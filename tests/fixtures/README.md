# Fixtures

- `synthetic_*.txt`: **synthetic** captures that mimic the structure of a LinkedIn page (menu,
  side list, markers, the signed-in user's name at the bottom). Safe to publish.
- Real captures go in `private/` (ignored by git). They contain your name and other people's
  data, so they never leave your machine. `test_trim.py` picks them up automatically.
