"""
SPED Fiscal Editor Pro 2.5 - Entry Point
Execute: python app.py
"""

import sys
import logging
from PyQt6.QtWidgets import QApplication

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='sped_editor_pro.log',
    filemode='a'
)

from sped.ui.main_window import MainWindow


def main():
    """Ponto de entrada da aplicação."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
