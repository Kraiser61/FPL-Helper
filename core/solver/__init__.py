"""
Open-FPL-Solver Integration Package for FPL Helper
Provides high-performance multi-period MIP optimization using HiGHS.
"""

from core.solver.data_parser import read_data
from core.solver.projection_generator import generate_builtin_projections
from core.solver.service import FPLSolverService
from core.solver.solver_engine import SolverResult, prep_data, solve_multi_period_fpl
from core.solver.utils import get_default_options, load_settings

__all__ = [
    "FPLSolverService",
    "SolverResult",
    "prep_data",
    "solve_multi_period_fpl",
    "read_data",
    "load_settings",
    "get_default_options",
    "generate_builtin_projections",
]
