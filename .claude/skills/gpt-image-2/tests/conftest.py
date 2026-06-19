"""pytest 共通設定: scripts ディレクトリを import パスに追加する。"""
import os
import sys

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
