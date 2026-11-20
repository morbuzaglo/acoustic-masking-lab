import sys, pathlib, os, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
# tests must never touch the user's real projects / scene library
os.environ.setdefault("AML_DATA_DIR", tempfile.mkdtemp(prefix="aml_test_data_"))
