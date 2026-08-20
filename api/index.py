import os, sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

os.chdir(_root)

from app import app as application
from mangum import Mangum

handler = Mangum(application)
