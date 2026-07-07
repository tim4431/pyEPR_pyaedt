"""
Tests for pyEPR_pyaedt.core_distributed_analysis that do not need a live HFSS
connection.
"""
from types import SimpleNamespace

import pytest


class TestDoEPRAnalysisGuards:
    """do_EPR_analysis must fail fast with a clear message on bad setup."""

    def _bare_instance(self, junctions):
        """Build a DistributedAnalysis without running __init__ (no COM)."""
        from pyEPR_pyaedt.core_distributed_analysis import DistributedAnalysis

        eprd = DistributedAnalysis.__new__(DistributedAnalysis)
        eprd.pinfo = SimpleNamespace(junctions=junctions)
        return eprd

    def test_no_junctions_raises_value_error(self):
        """Previously died with UnboundLocalError deep in calc_p_junction."""
        eprd = self._bare_instance(junctions={})
        with pytest.raises(ValueError, match="No junctions"):
            eprd.do_EPR_analysis()
