"""MOCK experiment rows for tests only. Not real papers or extractions."""

# P1 has two experiments, so it checks that papers are counted once.
# P3 and P5 have no dataset; P2 and P5 have no task (universe checks).
MOCK_ROWS = [
    {"paper_id": "MOCK-P1", "method_id": 1, "dataset_id": 1, "task_id": 1, "setting_id": None, "year": 2021},
    {"paper_id": "MOCK-P1", "method_id": 1, "dataset_id": 2, "task_id": 1, "setting_id": None, "year": 2021},
    {"paper_id": "MOCK-P2", "method_id": 1, "dataset_id": 1, "task_id": None, "setting_id": None, "year": 2022},
    {"paper_id": "MOCK-P3", "method_id": 2, "dataset_id": None, "task_id": 1, "setting_id": None, "year": 2023},
    {"paper_id": "MOCK-P4", "method_id": 2, "dataset_id": 2, "task_id": 2, "setting_id": None, "year": 2024},
    {"paper_id": "MOCK-P5", "method_id": 1, "dataset_id": None, "task_id": None, "setting_id": None, "year": 2025},
]
