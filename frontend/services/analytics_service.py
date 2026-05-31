from __future__ import annotations

from backend.analytics import report_generator, stats_engine
from backend.analytics.heatmap_generator import generate_heatmap_from_db, get_generator


class AnalyticsService:
    def load_view_model(
        self,
        *,
        date_from: str,
        date_to: str,
        time_basis: str,
        camera_id=None,
        rule_name=None,
        min_alarm_level=None,
        gender=None,
    ) -> dict:
        summary = stats_engine.get_summary(date_from, date_to, camera_id, min_alarm_level=min_alarm_level, gender=gender)
        total = int(summary.get("total_detections", 0) or 0)
        violations = int(summary.get("violations", 0) or 0)
        compliant = total - violations
        rate = (compliant / total * 100) if total > 0 else 100.0
        gender_rows = stats_engine.get_gender_violations(
            date_from=date_from,
            date_to=date_to,
            camera_id=camera_id,
            rule_name=rule_name,
            min_alarm_level=min_alarm_level,
            gender=gender,
        )
        gender_counts = {row.get("gender", "unknown"): int(row.get("count", 0) or 0) for row in gender_rows}

        heatmap = None
        heatmap_placeholder = "Select a camera to view heatmap"
        if camera_id is not None:
            gen = get_generator(camera_id)
            heatmap = gen.generate() if gen.has_data() else None
            if heatmap is None:
                heatmap = generate_heatmap_from_db(camera_id=camera_id, date_from=date_from, date_to=date_to)
            heatmap_placeholder = "No heatmap data in selected range"

        return {
            "stats": {
                "total": total,
                "violations": violations,
                "compliance_rate": rate,
                "identified": stats_engine.get_identified_count(
                    date_from=date_from,
                    date_to=date_to,
                    camera_id=camera_id,
                    rule_name=rule_name,
                    min_alarm_level=min_alarm_level,
                    gender=gender,
                ),
                "gendered": gender_counts.get("male", 0) + gender_counts.get("female", 0),
                "gender_counts": gender_counts,
            },
            "trend": stats_engine.get_compliance_trend(
                rule_name=rule_name,
                date_from=date_from,
                date_to=date_to,
                camera_id=camera_id,
                time_basis=time_basis,
                gender=gender,
            ),
            "hourly": stats_engine.get_hourly_violation_chart(
                date_from,
                date_to,
                camera_id=camera_id,
                rule_name=rule_name,
                min_alarm_level=min_alarm_level,
                time_basis=time_basis,
                gender=gender,
            ),
            "camera_activity": stats_engine.get_camera_activity_data(date_from, date_to, camera_id=camera_id),
            "heatmap": heatmap,
            "heatmap_placeholder": heatmap_placeholder,
            "top_violators": stats_engine.get_person_violations(
                date_from,
                date_to,
                camera_id=camera_id,
                rule_name=rule_name,
                min_alarm_level=min_alarm_level,
                limit=10,
                gender=gender,
            ),
        }

    def reset_heatmap(self, camera_id: int) -> None:
        get_generator(camera_id).reset()

    def export_pdf(self, path: str, **kwargs) -> None:
        report_generator.generate_report(path, **kwargs)
