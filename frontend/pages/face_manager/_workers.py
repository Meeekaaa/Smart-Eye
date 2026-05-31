from __future__ import annotations

import os
import uuid

from PySide6.QtCore import QThread, Signal

from backend.repository import db


class EnrollWorker(QThread):
    progress = Signal(str)
    done = Signal(bool, str)

    def __init__(
        self,
        images,
        name: str,
        department: str,
        authorized: bool,
        gender: str | None = None,
        national_id: str = "",
        address: str = "",
        country: str = "",
        birth_date: str = "",
        phone: str = "",
        email: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._images = images
        self._name = name
        self._department = department
        self._authorized = authorized
        self._gender = gender
        self._national_id = national_id
        self._address = address
        self._country = country
        self._birth_date = birth_date
        self._phone = phone
        self._email = email

    def run(self):
        try:
            import cv2
            from backend.models import model_loader
            from utils.embedding_utils import average_embeddings, embedding_to_bytes

            if model_loader._prewarm_thread is not None and model_loader._prewarm_thread.is_alive():
                self.progress.emit("Waiting for face model to finish loading...")
                model_loader._prewarm_thread.join()

            model = model_loader.get_face_model()
            if model is None or not model.is_loaded:
                self.done.emit(
                    False,
                    "Face recognition model is not loaded.\nOpen Models > Face Recognition to configure and load it.",
                )
                return

            self.progress.emit("Extracting face embeddings...")
            embeddings = []
            for img in self._images:
                try:
                    emb = model.get_embedding(img)
                except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                    emb = None
                if emb is not None:
                    embeddings.append(emb)

            if not embeddings:
                self.done.emit(
                    False,
                    "No face detected in the captured photos.\nMake sure your face is clearly visible and centered.",
                )
                return

            self.progress.emit(f"Got {len(embeddings)} embedding(s), computing average...")
            avg = average_embeddings(embeddings)
            if avg is None:
                self.done.emit(False, "Failed to compute average embedding from captures.")
                return

            try:
                emb_bytes = embedding_to_bytes(avg)
            except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as e:
                self.done.emit(False, f"Failed to convert embedding: {e}")
                return

            save_dir = os.path.abspath(os.path.join("data", "faces"))
            os.makedirs(save_dir, exist_ok=True)
            safe_name = self._name.replace(" ", "_").replace("/", "_")
            photo_path = os.path.join(save_dir, f"{uuid.uuid4().hex}_{safe_name}.jpg")
            ok = cv2.imwrite(photo_path, self._images[0])
            if not ok:
                self.done.emit(False, f"Failed to write photo to {photo_path}")
                return

            self.progress.emit("Saving to database...")
            db.add_face(
                self._name,
                self._department,
                emb_bytes,
                photo_path,
                1 if self._authorized else 0,
                "[]",
                address=self._address,
                country=self._country,
                birth_date=self._birth_date,
                phone=self._phone,
                email=self._email,
                national_id=self._national_id,
                embedding_model=getattr(model_loader.get_face_model(), "model_name", "") or "",
                gender=self._gender,
            )
            self.done.emit(
                True,
                f"Successfully enrolled {self._name} with {len(embeddings)} sample(s).",
            )
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as e:
            self.done.emit(False, str(e))

