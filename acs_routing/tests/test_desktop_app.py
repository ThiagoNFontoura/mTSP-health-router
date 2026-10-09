import tempfile
import unittest
from datetime import date
from pathlib import Path

from acs_routing.config import Config
from acs_routing.desktop_app import CAR_SPEED_KMH, format_plan, process_csv
from acs_routing.models import Family, Route, WeekState
from acs_routing.reports import weekly_report
from acs_routing.travel_matrix import TravelMatrix


CSV_TEXT = """id,lat,lon,bedridden,physical_disability,mental_disability,poor_sanitation,severe_malnutrition,drug_addiction,unemployment,illiteracy,under_6_months,over_70_years,hypertension,diabetes,people_per_room
1,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1
2,-23.5510,-46.6310,1,0,0,0,0,0,0,0,0,0,0,0,1
"""

FIVE_FAMILIES_CSV = """id,lat,lon,bedridden,physical_disability,mental_disability,poor_sanitation,severe_malnutrition,drug_addiction,unemployment,illiteracy,under_6_months,over_70_years,hypertension,diabetes,people_per_room,last_visit_date
1,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,2026-07-07
2,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,2026-07-07
3,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,2026-07-07
4,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,2026-07-07
5,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,2026-07-07
"""

FIXED_FAMILIES_CSV = """id,lat,lon,bedridden,physical_disability,mental_disability,poor_sanitation,severe_malnutrition,drug_addiction,unemployment,illiteracy,under_6_months,over_70_years,hypertension,diabetes,people_per_room,fixed_day,fixed_period_weeks,fixed_phase_weeks,last_visit_date
1,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,2026-07-07
2,-23.5500,-46.6300,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,0,2026-07-07
"""


class DesktopAppTest(unittest.TestCase):
    def test_local_matrix_is_symmetric_and_has_zero_diagonal(self) -> None:
        matrix = TravelMatrix.from_coordinates(
            [(-23.55, -46.63), (-23.551, -46.631)]
        )
        self.assertEqual(matrix.seconds(0, 0), 0.0)
        self.assertAlmostEqual(matrix.seconds(0, 1), matrix.seconds(1, 0))
        self.assertGreater(matrix.seconds(0, 1), 0.0)

    def test_desktop_uses_car_speed(self) -> None:
        self.assertEqual(CAR_SPEED_KMH, 30.0)

    def test_process_and_format_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "families.csv"
            path.write_text(CSV_TEXT, encoding="utf-8")
            config = Config(week_days=1, n_iter=1, max_passes=2)
            families, state = process_csv(
                path,
                2,
                shift_minutes=360,
                config=config,
            )
            output = format_plan(families, state, 2)

        self.assertIn("AGENTE 1", output)
        self.assertIn("AGENTE 2", output)
        self.assertNotIn("endereço", output)
        self.assertIn("prioridade R", output)
        self.assertIn("Dia 5 — nenhuma visita programada", output)
        self.assertEqual(
            sorted(
                family_id
                for route in state.routes
                for family_id in route.sequence
                if family_id != 0
            ),
            [1, 2],
        )

    def test_active_time_limits_each_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "families.csv"
            path.write_text(CSV_TEXT, encoding="utf-8")
            config = Config(week_days=1, n_iter=1, max_passes=2)
            _, state = process_csv(
                path,
                1,
                shift_minutes=25,
                config=config,
            )

        self.assertTrue(
            all(
                route.total_time <= 25
                for route in state.routes
            )
        )

    def test_normalizes_date_and_fills_zero_reward_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "families.csv"
            path.write_text(FIVE_FAMILIES_CSV, encoding="utf-8")
            config = Config(
                week_days=5,
                n_iter=1,
                max_passes=2,
                initial_date=date(2026, 10, 8),
            )
            families, state = process_csv(
                path,
                1,
                shift_minutes=10,
                config=config,
            )

        planned = [
            family_id
            for route in state.routes
            for family_id in route.sequence
            if family_id != 0
        ]
        day_five = next(route for route in state.routes if route.day == 5)
        self.assertEqual(state.monday_date, date(2026, 10, 5))
        self.assertEqual(sorted(planned), [family.id for family in families])
        self.assertEqual(len(planned), len(set(planned)))
        self.assertNotEqual(day_five.sequence, [0, 0])
        self.assertTrue(all(route.total_time <= 10 for route in state.routes))

    def test_capacity_fill_keeps_active_fixed_families_on_fixed_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "families.csv"
            path.write_text(FIXED_FAMILIES_CSV, encoding="utf-8")
            config = Config(
                week_days=5,
                n_iter=1,
                max_passes=2,
                initial_date=date(2026, 10, 5),
            )
            _, state = process_csv(
                path,
                1,
                shift_minutes=10,
                config=config,
            )

        planned = [
            (route.day, family_id)
            for route in state.routes
            for family_id in route.sequence
            if family_id != 0
        ]
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0][0], 1)

    def test_report_metrics_cover_risk_fixed_day_and_interval_status(self) -> None:
        config = Config(
            week_days=4,
            agents_per_day=1,
            initial_date=date(2026, 10, 5),
        )
        families = [
            Family(1, 0.0, 0.0, {}, "R1", None, date(2026, 7, 1)),
            Family(2, 0.0, 0.0, {}, "R1", None, date(2026, 10, 1)),
            Family(3, 0.0, 0.0, {}, "R2", None, date(2026, 1, 1)),
            Family(4, 0.0, 0.0, {}, "R3", None, date(2026, 1, 1)),
            Family(5, 0.0, 0.0, {}, "R0", 3, date(2026, 1, 1)),
            Family(6, 0.0, 0.0, {}, "R0", 5, date(2026, 1, 1)),
        ]
        state = WeekState(
            families,
            [Route([0, 1, 5, 0], day=1, agent=1)],
            date(2026, 10, 5),
        )

        report = weekly_report(families, state, config)

        self.assertEqual(report["risk_family_visit_percentages"]["R1"], 50.0)
        self.assertEqual(report["risk_family_visit_percentages"]["R2"], 0.0)
        self.assertEqual(report["risk_family_visit_percentages"]["R3"], 0.0)
        self.assertEqual(report["active_fixed_not_served"], 1)
        self.assertEqual(report["overdue_not_served"], 2)
        self.assertEqual(report["max_overdue_days_since_last_visit"], 277)

        output = format_plan(families, state, 1, config)
        self.assertIn("R1: 1 de 2 famílias visitadas (50.0%)", output)
        self.assertIn("Famílias de dia fixo não atendidas no dia previsto: 1", output)
        self.assertIn(
            "Famílias atrasadas por intervalo entre visitas não atendidas: 2",
            output,
        )
        self.assertIn(
            "Maior atraso entre as famílias não atendidas: "
            "277 dias desde a última visita",
            output,
        )


if __name__ == "__main__":
    unittest.main()
