import logging

from backend.pipeline.alarm_handler import get_handler
from backend.pipeline.escalation_manager import get_escalation_manager


logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(self, camera_id: int):
        self._camera_id = camera_id
        self._escalation = get_escalation_manager()
        self._alarm = get_handler()

    def handle_result(
        self,
        result: dict,
        frame,
        *,
        infer_fw: int,
        infer_fh: int,
        enable_inbox: bool = False,
        enable_heatmap: bool = False,
        inbox_context=None,
        on_detection_event=None,
    ) -> dict:
        triggered = result.pop("_triggered", [])
        if triggered:
            self._escalation.update(self._camera_id, triggered)
            levels = self._escalation.get_escalation_levels(self._camera_id, triggered)
            self._alarm.handle_alarms(triggered, levels, result, frame)
            if on_detection_event is not None:
                try:
                    on_detection_event(triggered, result)
                except Exception:
                    logger.exception("Detection event callback failed")
        else:
            self._escalation.update(self._camera_id, [])
            self._alarm.handle_alarms([], {}, result, frame)

        result["triggered_rules"] = [r["name"] for r in triggered]
        result["active_violations"] = self._escalation.get_active_violations(self._camera_id)

        if enable_inbox:
            try:
                from backend.camera.inbox_capture import capture_unknown_faces

                if inbox_context is None:
                    logger.warning("Inbox capture requested without context; skipping")
                else:
                    capture_unknown_faces(inbox_context, frame, result)
            except Exception:
                logger.exception("capture_unknown_faces failed")

        if enable_heatmap:
            try:
                from backend.analytics.heatmap_generator import get_generator

                gen = get_generator(self._camera_id)
                for face in result.get("all_faces", []):
                    if face.get("_coasted"):
                        continue
                    bbox = face.get("bbox")
                    if bbox:
                        gen.add_detection(bbox, infer_fw, infer_fh)
                for obj in result.get("object_bboxes", []):
                    if obj.get("_coasted"):
                        continue
                    bbox = obj.get("bbox")
                    if bbox:
                        gen.add_detection(bbox, infer_fw, infer_fh)
            except Exception:
                logger.exception("Heatmap generation failed")

        return result
