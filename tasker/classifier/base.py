"""
tasker.classifier.base
-----------------------
ClassifierBase ABC.
See SDD Sections 5.2 and 7.3.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

# TODO Phase 1
#
# class ClassifierBase(ABC):
#     @abstractmethod
#     async def classify(self, task: str, mode) -> ClassifierResult: ...