CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symptom TEXT NOT NULL,
  severity INTEGER NOT NULL,
  notes TEXT,
  triggers TEXT,
  meds TEXT,
  sleep_hours REAL,
  stress INTEGER,
  time_of_day TEXT,
  pain INTEGER,
  global_health INTEGER,
  top_culprit TEXT,
  analysis_json TEXT,
  entry_json TEXT
);
