"""
SPED Fiscal Editor - Pacote principal
"""

__version__ = "2.8.0"
__author__ = "SPED Editor Team"

from .models import SpedSummaryData, SpedRecord, SPED_LAYOUT
from .utils import validate_reg_type, sanitize_reg_type, parse_float
from .parser import process_sped_summary, process_sped_detailed
from .database import SpedManager
from .pdf_generator import generate_cfop_analysis_pdf, generate_consolidated_pdf
from .history import EditHistory, EditOperation
from .dashboard import generate_dashboard_data, DashboardData
from .exporter import (export_to_csv, export_to_excel, 
                        export_all_to_excel, export_all_to_csv)
from .validation import validate_sped, ValidationResult, Severity

__all__ = [
    "SpedSummaryData",
    "SpedRecord",
    "SPED_LAYOUT",
    "validate_reg_type",
    "sanitize_reg_type",
    "parse_float",
    "process_sped_summary",
    "process_sped_detailed",
    "SpedManager",
    "generate_cfop_analysis_pdf",
    "generate_consolidated_pdf",
    "EditHistory",
    "EditOperation",
    "generate_dashboard_data",
    "DashboardData",
    "export_to_csv",
    "export_to_excel",
    "export_all_to_excel",
    "export_all_to_csv",
    "validate_sped",
    "ValidationResult",
    "Severity",
]
