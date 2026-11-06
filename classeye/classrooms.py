"""Classrooms and their student datasets.

On disk (data/classes/<class id>/):
    class.json          {"name": "AIML B Section", "created": "..."}
    students.json       [{"usn": "4AL22AI001", "name": "Asha"}, ...]
    photos/<USN>/       face photos of that student (jpg/png)
    .faces.npz          cached face embeddings (rebuilt automatically when photos change)

The class id never changes, so renaming a class ("AIML A" -> "AIML B Section") is safe.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from .faces import mirror_row
from .settings import classes_dir

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


@dataclass
class Student:
    usn: str
    name: str
    class_id: str = ""
    class_name: str = ""
    photos: list = field(default_factory=list)


@dataclass
class ClassRoom:
    id: str
    name: str
    folder: str

    @property
    def photos_dir(self):
        return os.path.join(self.folder, "photos")


def read_image(path):
    data = np.fromfile(path, dtype=np.uint8)   # works with non-English Windows paths
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def write_image(path, image, quality=92):
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        buf.tofile(path)
    return ok


def clean_usn(usn: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", (usn or "").strip()).upper()


# =============================================================================
class ClassRepository:
    def __init__(self, root=None):
        self.root = root or classes_dir()
        os.makedirs(self.root, exist_ok=True)

    # ---- classes -----------------------------------------------------------
    def list(self):
        out = []
        for cid in sorted(os.listdir(self.root)):
            folder = os.path.join(self.root, cid)
            meta = os.path.join(folder, "class.json")
            if os.path.isdir(folder) and os.path.exists(meta):
                try:
                    with open(meta, encoding="utf-8") as f:
                        name = json.load(f).get("name", cid)
                except (OSError, ValueError):
                    name = cid
                out.append(ClassRoom(cid, name, folder))
        return sorted(out, key=lambda c: c.name.lower())

    def get(self, class_id):
        for c in self.list():
            if c.id == class_id:
                return c
        raise KeyError(class_id)

    def create(self, name):
        name = name.strip()
        if not name:
            raise ValueError("Class name cannot be empty")
        if any(c.name.lower() == name.lower() for c in self.list()):
            raise ValueError(f"A class called '{name}' already exists")
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "class"
        cid, n = base, 2
        while os.path.exists(os.path.join(self.root, cid)):
            cid, n = f"{base}-{n}", n + 1
        folder = os.path.join(self.root, cid)
        os.makedirs(os.path.join(folder, "photos"))
        self._write_json(os.path.join(folder, "class.json"),
                         {"name": name, "created": time.strftime("%Y-%m-%d %H:%M")})
        self._write_json(os.path.join(folder, "students.json"), [])
        return ClassRoom(cid, name, folder)

    def rename(self, class_id, new_name):
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Class name cannot be empty")
        if any(c.name.lower() == new_name.lower() and c.id != class_id for c in self.list()):
            raise ValueError(f"A class called '{new_name}' already exists")
        c = self.get(class_id)
        meta_path = os.path.join(c.folder, "class.json")
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["name"] = new_name
        self._write_json(meta_path, meta)

    def delete(self, class_id):
        shutil.rmtree(self.get(class_id).folder)

    # ---- students ----------------------------------------------------------
    def students(self, class_id):
        c = self.get(class_id)
        try:
            with open(os.path.join(c.folder, "students.json"), encoding="utf-8") as f:
                rows = json.load(f)
        except (OSError, ValueError):
            rows = []
        out = []
        for r in rows:
            st = Student(r["usn"], r.get("name", r["usn"]), c.id, c.name)
            st.photos = self.photos_of(c, st.usn)
            out.append(st)
        return out

    def photos_of(self, classroom, usn):
        d = os.path.join(classroom.photos_dir, usn)
        if not os.path.isdir(d):
            return []
        return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(IMAGE_EXT)]

    def _save_students(self, classroom, students):
        rows = [{"usn": s.usn, "name": s.name} for s in sorted(students, key=lambda s: s.usn)]
        self._write_json(os.path.join(classroom.folder, "students.json"), rows)

    def add_student(self, class_id, usn, name):
        usn = clean_usn(usn)
        if not usn:
            raise ValueError("USN is required")
        c = self.get(class_id)
        studs = self.students(class_id)
        for s in studs:
            if s.usn == usn:
                s.name = name.strip() or s.name   # update name
                self._save_students(c, studs)
                return s
        st = Student(usn, name.strip() or usn, c.id, c.name)
        studs.append(st)
        os.makedirs(os.path.join(c.photos_dir, usn), exist_ok=True)
        self._save_students(c, studs)
        return st

    def remove_student(self, class_id, usn):
        c = self.get(class_id)
        studs = [s for s in self.students(class_id) if s.usn != usn]
        self._save_students(c, studs)
        shutil.rmtree(os.path.join(c.photos_dir, usn), ignore_errors=True)

    def add_photo(self, class_id, usn, image=None, file_path=None):
        """Save a photo (numpy image or an existing file) for a student. Returns the saved path."""
        c = self.get(class_id)
        d = os.path.join(c.photos_dir, usn)
        os.makedirs(d, exist_ok=True)
        n = len([f for f in os.listdir(d) if f.lower().endswith(IMAGE_EXT)]) + 1
        dest = os.path.join(d, f"{usn}_{n:02d}.jpg")
        while os.path.exists(dest):
            n += 1
            dest = os.path.join(d, f"{usn}_{n:02d}.jpg")
        if image is None:
            image = read_image(file_path)
            if image is None:
                raise ValueError(f"Cannot read image {file_path}")
        h, w = image.shape[:2]
        if max(h, w) > 1600:
            s = 1600 / max(h, w)
            image = cv2.resize(image, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        write_image(dest, image)
        return dest

    def import_students(self, class_id, sheet_path, photos_folder=None):
        """Import USN/Name from .csv or .xlsx; optional photo folder with <USN>.jpg or <USN>/ subfolders."""
        rows = _read_sheet(sheet_path)
        added = 0
        for usn, name in rows:
            if not clean_usn(usn):
                continue
            st = self.add_student(class_id, usn, name)
            added += 1
            if photos_folder and os.path.isdir(photos_folder):
                for p in _photos_for(photos_folder, st.usn):
                    self.add_photo(class_id, st.usn, file_path=p)
        return added

    @staticmethod
    def _write_json(path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


def _read_sheet(path):
    rows = []
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        ws = load_workbook(path, read_only=True, data_only=True).active
        it = ws.iter_rows(values_only=True)
        header = [str(h or "").strip().lower() for h in next(it)]
        iu = next(i for i, h in enumerate(header) if "usn" in h or h in ("id", "roll"))
        iname = next(i for i, h in enumerate(header) if "name" in h)
        for r in it:
            if r and r[iu]:
                rows.append((str(r[iu]), str(r[iname] or "")))
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                usn = next((v for k, v in r.items() if "usn" in k), "")
                name = next((v for k, v in r.items() if "name" in k), "")
                rows.append((usn, name))
    return rows


def _photos_for(folder, usn):
    out = []
    sub = os.path.join(folder, usn)
    if os.path.isdir(sub):
        out += [os.path.join(sub, f) for f in sorted(os.listdir(sub)) if f.lower().endswith(IMAGE_EXT)]
    for f in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(f)
        if ext.lower() in IMAGE_EXT and (stem.upper() == usn or stem.upper().startswith(usn + "_")):
            out.append(os.path.join(folder, f))
    return out


# =============================================================================
class FaceGallery:
    """Embeddings of every enrolled student, searchable by cosine similarity.

    Rows for one student are contiguous; best_per_student() takes the maximum
    similarity over all of that student's photos.
    """

    def __init__(self, students, vectors, owner):
        self.students = students
        self.vectors = vectors.astype(np.float32) if len(vectors) else np.zeros((0, 128), np.float32)
        self.owner = np.asarray(owner, np.int64)
        self._starts = np.searchsorted(self.owner, np.arange(len(students))) if len(students) else None

    def __len__(self):
        return len(self.students)

    def best_per_student(self, queries):
        if len(self.students) == 0 or len(queries) == 0:
            return np.zeros((len(queries), len(self.students)), np.float32)
        sims = np.asarray(queries, np.float32) @ self.vectors.T
        return np.maximum.reduceat(sims, self._starts, axis=1)

    def identify(self, vector, threshold, margin):
        """(student, similarity) or (None, similarity)."""
        if vector is None or len(self.students) == 0:
            return None, 0.0
        s = self.best_per_student([vector])[0]
        order = np.argsort(-s)
        best = float(s[order[0]])
        second = float(s[order[1]]) if len(order) > 1 else -1.0
        if best >= threshold and best - second >= margin:
            return self.students[int(order[0])], best
        return None, best

    @staticmethod
    def merge(galleries):
        studs, vecs, owner = [], [], []
        for g in galleries:
            for i, st in enumerate(g.students):
                rows = g.vectors[g.owner == i]
                if len(rows):
                    owner += [len(studs)] * len(rows)
                    vecs.append(rows)
                    studs.append(st)
        return FaceGallery(studs, np.concatenate(vecs) if vecs else np.zeros((0, 128)), owner)


def _photo_key(path):
    st = os.stat(path)
    return hashlib.sha1(f"{os.path.basename(path)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()


def build_gallery(repo, class_id, engine, progress=None):
    """Embeddings for one class (cached). Returns (gallery, all_students, warnings)."""
    c = repo.get(class_id)
    students = repo.students(class_id)
    cache_path = os.path.join(c.folder, ".faces.npz")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with np.load(cache_path) as d:
                cache = {k: d[k] for k in d.files}
        except Exception:
            cache = {}
    new_cache, warnings = {}, []
    enrolled, vecs, owner = [], [], []
    for i, st in enumerate(students):
        if progress:
            progress(i, len(students), st.name)
        rows = []
        if not st.photos:
            warnings.append(f"{st.usn} {st.name}: no photo")
        for p in st.photos:
            try:
                key = _photo_key(p)
            except OSError:
                continue
            v = cache.get(key)
            if v is None:
                img = read_image(p)
                row = engine.main_face(img) if img is not None else None
                if row is None:
                    warnings.append(f"{st.usn} {st.name}: no face found in {os.path.basename(p)}")
                    v = np.zeros((0, 128), np.float32)
                else:
                    flipped = cv2.flip(img, 1)
                    v = np.stack([engine.embed(img, row),
                                  engine.embed(flipped, mirror_row(row, img.shape[1]))])
            new_cache[key] = v
            if len(v):
                rows.append(v)
        if rows:
            owner += [len(enrolled)] * sum(len(r) for r in rows)
            vecs += rows
            enrolled.append(st)
        elif st.photos:
            warnings.append(f"{st.usn} {st.name}: no usable photo - add a clearer one")
    try:
        np.savez(cache_path, **new_cache)
    except OSError:
        pass
    gallery = FaceGallery(enrolled, np.concatenate(vecs) if vecs else np.zeros((0, 128)), owner)
    return gallery, students, warnings
