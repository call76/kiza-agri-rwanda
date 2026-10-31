import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db; db.init()
from kiza8 import schema, pipeline
schema.migrate(); print("run id:", pipeline.import_nisr_csv(sys.argv[1]))
