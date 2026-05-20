"""Shared pytest fixtures for NewsLingo tests."""
import os
import sys

# Ensure the project root is on sys.path so scrapers and project modules import cleanly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
