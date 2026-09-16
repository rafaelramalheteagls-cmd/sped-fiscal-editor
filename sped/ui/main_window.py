"""
Módulo da janela principal do editor SPED Fiscal.
Contém a interface gráfica principal.
"""

import sys
import os
import subprocess
import logging
from typing import Dict, List, Optional

import pandas as pd
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTreeWidget,
                             QTreeWidgetItem, QTableWidget, QTableWidgetItem,
                             QTabWidget, QFileDialog, QMessageBox, QTextEdit,
                             QPushButton, QSplitter, QLabel, QLineEdit,
                             QProgressBar, QHBoxLayout, QInputDialog,
                             QGroupBox, QGridLayout, QFrame, QComboBox,
                             QCheckBox, QHeaderView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QShortcut, QColor, QKeySequence, QFont

from ..database import SpedManager
from ..parser import process_sped_summary
from ..pdf_generator import generate_cfop_analysis_pdf, generate_consolidated_pdf
from ..pdf_preview import show_pdf_preview
from ..dashboard import generate_dashboard_data, DashboardData
from ..exporter import (export_to_csv, export_to_excel, 
                        export_all_to_excel, export_all_to_csv)
from ..validation import validate_sped, ValidationResult, Severity

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Janela principal do editor SPED."""
    
    PAGE_SIZE: int = 1000  # Itens por página na visualização
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SPED Fiscal Editor Pro 2.6 - Versao com Undo/Redo e Dashboard")
        self.resize(1400, 900)
        self.manager = SpedManager()
        self.current_reg: Optional[str] = None
        self.current_page: int = 0
        self.total_pages: int = 0
        self.setup_ui()
        self.setup_shortcuts()
    
    def closeEvent(self, event) -> None:
        """Evento de fechamento da janela."""
        self.manager.close()
        event.accept()
    
    def setup_shortcuts(self) -> None:
        """Configura atalhos de teclado."""
        # Undo: Ctrl+Z
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self.undo_action)
        
        # Redo: Ctrl+Y ou Ctrl+Shift+Z
        redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut.activated.connect(self.redo_action)
        
        redo_shortcut2 = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        redo_shortcut2.activated.connect(self.redo_action)
        
        # Importar: Ctrl+I
        import_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        import_shortcut.activated.connect(self.import_sped)
        
        # Exportar: Ctrl+E
        export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        export_shortcut.activated.connect(self.export_sped)
    
    def setup_ui(self) -> None:
        """Configura a interface do usuário."""
        menubar = self.menuBar()
        
        # Menu Arquivo
        file_menu = menubar.addMenu("Arquivo")
        file_menu.addAction("Importar SPED", self.import_sped)
        file_menu.addSeparator()
        file_menu.addAction("Importar CTE XML", self.import_cte_xml)
        file_menu.addSeparator()
        
        # Submenu Exportar SPED
        export_sped_menu = file_menu.addMenu("Exportar SPED")
        export_sped_menu.addAction("Exportar como TXT", self.export_sped)
        
        file_menu.addSeparator()
        
        # Submenu Exportar Dados
        export_menu = file_menu.addMenu("Exportar Dados")
        export_menu.addAction("Selecionado → Excel", self.export_current_to_excel)
        export_menu.addAction("Selecionado → CSV", self.export_current_to_csv)
        export_menu.addSeparator()
        export_menu.addAction("Todos → Excel (1 arquivo)", self.export_all_to_excel_action)
        export_menu.addAction("Todos → CSV (pasta)", self.export_all_to_csv_action)
        
        file_menu.addSeparator()
        file_menu.addAction("Sair", self.close)
        
        # Menu Edição
        edit_menu = menubar.addMenu("Edição")
        self.undo_action_menu = edit_menu.addAction("Desfazer (Ctrl+Z)")
        self.undo_action_menu.triggered.connect(self.undo_action)
        self.redo_action_menu = edit_menu.addAction("Refazer (Ctrl+Y)")
        self.redo_action_menu.triggered.connect(self.redo_action)
        edit_menu.addSeparator()
        self.undo_action_menu.setEnabled(False)
        self.redo_action_menu.setEnabled(False)
        
        # Menu Análise
        analysis_menu = menubar.addMenu("Análise")
        analysis_menu.addAction("Dashboard", self.show_dashboard)
        analysis_menu.addSeparator()
        analysis_menu.addAction("Validar SPED (PVA)", self.run_validation)
        analysis_menu.addSeparator()
        
        # Submenu Relatórios PDF
        pdf_menu = analysis_menu.addMenu("Relatórios PDF")
        pdf_menu.addAction("Um PDF por CFOP", self.generate_cfop_reports)
        pdf_menu.addSeparator()
        pdf_menu.addAction("Consolidado: Todas as Entradas", self.generate_entrada_report)
        pdf_menu.addAction("Consolidado: Todas as Saídas", self.generate_saida_report)
        pdf_menu.addAction("Consolidado: Entradas + Saídas", self.generate_all_reports)
        
        analysis_menu.addSeparator()
        analysis_menu.addAction("Resumo por CFOP", self.show_cfop_summary)
        
        # Status Bar
        self.status_bar = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress)
        self.status_label = QLabel("Pronto.")
        self.status_bar.addWidget(self.status_label)
        
        # Label de undo/redo
        self.lbl_history = QLabel("Histórico: 0/0")
        self.status_bar.addPermanentWidget(self.lbl_history)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)
        
        # Painel esquerdo - Árvore de registros
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filtrar blocos (ex: C100)...")
        self.search_box.textChanged.connect(self.filter_tree)
        left_layout.addWidget(self.search_box)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Estrutura SPED")
        self.tree.itemClicked.connect(self.on_tree_click)
        left_layout.addWidget(self.tree)
        
        splitter.addWidget(left_widget)
        splitter.setSizes([250, 1150])
        
        # Painel direito - Abas
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        
        # Aba 1: Editor
        self.grid_w = QWidget()
        vbox = QVBoxLayout(self.grid_w)
        
        hbox_top = QHBoxLayout()
        self.lbl_info = QLabel("Nenhum arquivo carregado.")
        hbox_top.addWidget(self.lbl_info)
        
        btn_fix_0200 = QPushButton("Corrigir Espacos (0200)")
        btn_fix_0200.setToolTip("Remove espacos duplos ou em branco no inicio/fim da descricao.")
        btn_fix_0200.clicked.connect(self.fix_0200_action)
        hbox_top.addWidget(btn_fix_0200)
        
        btn_fix_h005 = QPushButton("Ajustar Inventario (H005/H010)")
        btn_fix_h005.setToolTip("Recalcula itens do inventario para atingir o valor exato desejado.")
        btn_fix_h005.clicked.connect(self.fix_inventory_action)
        hbox_top.addWidget(btn_fix_h005)
        
        vbox.addLayout(hbox_top)
        
        # Controles de paginação
        hbox_pagination = QHBoxLayout()
        self.btn_prev = QPushButton("Anterior")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_prev.setEnabled(False)
        hbox_pagination.addWidget(self.btn_prev)
        
        self.lbl_page = QLabel("Pagina 0/0")
        hbox_pagination.addWidget(self.lbl_page)
        
        self.btn_next = QPushButton("Proximo")
        self.btn_next.clicked.connect(self.next_page)
        self.btn_next.setEnabled(False)
        hbox_pagination.addWidget(self.btn_next)
        
        self.lbl_total_rows = QLabel("Total: 0 registros")
        hbox_pagination.addWidget(self.lbl_total_rows)
        hbox_pagination.addStretch()
        
        vbox.addLayout(hbox_pagination)
        
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self.on_cell_changed)
        vbox.addWidget(self.table)
        self.tabs.addTab(self.grid_w, "Editor de Registros")
        
        # Aba 2: Analise por CFOP
        self.cfop_w = QWidget()
        vbox_cfop = QVBoxLayout(self.cfop_w)
        vbox_cfop.addWidget(QLabel("Analise de CFOP - Entradas"))
        self.table_cfop_entrada = QTableWidget()
        vbox_cfop.addWidget(self.table_cfop_entrada)
        vbox_cfop.addWidget(QLabel("Analise de CFOP - Saidas"))
        self.table_cfop_saida = QTableWidget()
        vbox_cfop.addWidget(self.table_cfop_saida)
        self.tabs.addTab(self.cfop_w, "Analise por CFOP")
        
        # Aba 3: SQL
        self.sql_w = QWidget()
        vbox_sql = QVBoxLayout(self.sql_w)
        vbox_sql.addWidget(QLabel("Consulta SQL"))
        self.txt_sql = QTextEdit()
        self.txt_sql.setMaximumHeight(100)
        self.txt_sql.setPlaceholderText("Digite sua consulta SQL aqui...")
        vbox_sql.addWidget(self.txt_sql)
        btn_sql = QPushButton("Executar SQL")
        btn_sql.clicked.connect(self.run_sql)
        vbox_sql.addWidget(btn_sql)
        self.table_sql = QTableWidget()
        vbox_sql.addWidget(self.table_sql)
        self.tabs.addTab(self.sql_w, "Modo Avançado (SQL)")
        
        # Aba 4: Dashboard
        self.dashboard_w = QWidget()
        self.setup_dashboard_tab()
        self.tabs.addTab(self.dashboard_w, "Dashboard")
        
        # Aba 5: Busca Global
        self.search_w = QWidget()
        self.setup_search_tab()
        self.tabs.addTab(self.search_w, "Busca Global")
        
        # Aba 6: Validação Fiscal
        self.validation_w = QWidget()
        self.setup_validation_tab()
        self.tabs.addTab(self.validation_w, "Validação Fiscal")
    
    def setup_validation_tab(self) -> None:
        """Configura a aba de Validação Fiscal."""
        layout = QVBoxLayout(self.validation_w)
        
        # Título
        title = QLabel("Validação Fiscal - Regras PVA/SEFAZ")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        layout.addWidget(title)
        
        # Grupo de ações
        grp_actions = QGroupBox("Ações de Validação")
        hbox_actions = QHBoxLayout(grp_actions)
        
        btn_validate = QPushButton("✅ Executar Validação")
        btn_validate.setStyleSheet("font-weight: bold; padding: 8px 15px; background-color: #90EE90;")
        btn_validate.clicked.connect(self.run_validation)
        hbox_actions.addWidget(btn_validate)
        
        self.lbl_validation_status = QLabel("Nenhuma validação executada")
        self.lbl_validation_status.setStyleSheet("font-weight: bold;")
        hbox_actions.addWidget(self.lbl_validation_status)
        
        layout.addWidget(grp_actions)
        
        # Grupo de limpeza
        grp_clean = QGroupBox("Limpeza de Dados")
        hbox_clean = QHBoxLayout(grp_clean)
        
        btn_clean_0200 = QPushButton("🧹 Limpar Registro 0200 (Produtos Não Utilizados)")
        btn_clean_0200.setStyleSheet("font-weight: bold; padding: 8px 15px; background-color: #FFB6C1;")
        btn_clean_0200.setToolTip("Remove registros 0200 que não estão sendo usados em C170 ou H010")
        btn_clean_0200.clicked.connect(self.clean_unused_0200)
        hbox_clean.addWidget(btn_clean_0200)
        
        self.lbl_clean_status = QLabel("")
        self.lbl_clean_status.setStyleSheet("font-weight: bold;")
        hbox_clean.addWidget(self.lbl_clean_status)
        
        layout.addWidget(grp_clean)
        
        # Resumo
        grp_summary = QGroupBox("Resumo da Validação")
        grid_summary = QGridLayout(grp_summary)
        
        self.lbl_total_records = QLabel("0")
        self.lbl_errors_count = QLabel("0")
        self.lbl_warnings_count = QLabel("0")
        
        self.lbl_errors_count.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.lbl_warnings_count.setStyleSheet("color: orange; font-size: 16px; font-weight: bold;")
        
        grid_summary.addWidget(QLabel("Total de Registros:"), 0, 0)
        grid_summary.addWidget(self.lbl_total_records, 0, 1)
        grid_summary.addWidget(QLabel("Erros:"), 0, 2)
        grid_summary.addWidget(self.lbl_errors_count, 0, 3)
        grid_summary.addWidget(QLabel("Advertências:"), 0, 4)
        grid_summary.addWidget(self.lbl_warnings_count, 0, 5)
        
        layout.addWidget(grp_summary)
        
        # Lista de problemas
        grp_issues = QGroupBox("Problemas Encontrados")
        vbox_issues = QVBoxLayout(grp_issues)
        
        self.table_validation = QTableWidget()
        self.table_validation.setAlternatingRowColors(True)
        self.table_validation.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_validation.setColumnCount(5)
        self.table_validation.setHorizontalHeaderLabels([
            "Severidade", "Código", "Registro", "Campo", "Mensagem"
        ])
        self.table_validation.horizontalHeader().setStretchLastSection(True)
        self.table_validation.setColumnWidth(0, 100)
        self.table_validation.setColumnWidth(1, 80)
        self.table_validation.setColumnWidth(2, 80)
        self.table_validation.setColumnWidth(3, 100)
        vbox_issues.addWidget(self.table_validation)
        
        layout.addWidget(grp_issues)
    
    def run_validation(self) -> None:
        """Executa a validação fiscal do SPED."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        self.status_label.setText("Executando validação fiscal...")
        self.lbl_validation_status.setText("Validando...")
        
        try:
            result = validate_sped(self.manager._conn)
            
            # Atualizar resumo
            self.lbl_total_records.setText(str(result.total_records))
            self.lbl_errors_count.setText(str(len(result.errors)))
            self.lbl_warnings_count.setText(str(len(result.warnings)))
            
            # Atualizar status
            if result.has_errors:
                self.lbl_validation_status.setText(
                    f"❌ {len(result.errors)} ERRO(S) encontrado(s)"
                )
                self.lbl_validation_status.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.lbl_validation_status.setText(
                    f"✅ Validação OK - {len(result.warnings)} advertência(s)"
                )
                self.lbl_validation_status.setStyleSheet("color: green; font-weight: bold;")
            
            # Preencher tabela de problemas
            self._populate_validation_table(result)
            
            # Mostrar aba de validação
            self.tabs.setCurrentWidget(self.validation_w)
            
            self.status_label.setText("Validação concluída.")
            
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao executar validação: {str(e)}")
            logger.error(f"Erro na validação: {e}")
    
    def clean_unused_0200(self) -> None:
        """Limpa registros 0200 não utilizados em C170 ou H010."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        # Confirmar com o usuário
        reply = QMessageBox.question(
            self,
            "Confirmar Limpeza",
            "Deseja remover os registros 0200 (produtos) que não estão sendo "
            "utilizados nos registros C170 (itens de notas) ou H010 (inventário)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        self.status_label.setText("Executando limpeza do registro 0200...")
        self.lbl_clean_status.setText("Limpando...")
        
        try:
            total, removidos, itens_removidos = self.manager.clean_unused_0200()
            
            if total == 0:
                self.lbl_clean_status.setText("Nenhum registro 0200 encontrado")
                self.lbl_clean_status.setStyleSheet("color: gray; font-weight: bold;")
            elif removidos == 0:
                self.lbl_clean_status.setText(
                    f"✅ Nenhum registro removido ({total} itens estão em uso)"
                )
                self.lbl_clean_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.lbl_clean_status.setText(
                    f"✅ {removidos}/{total} registros removidos"
                )
                self.lbl_clean_status.setStyleSheet("color: orange; font-weight: bold;")
                
                # Mostrar detalhes
                msg = f"Registros 0200 removidos: {removidos}/{total}\n\n"
                msg += "Itens removidos:\n"
                for item in itens_removidos[:20]:  # Limitar a 20 itens
                    msg += f"• {item}\n"
                if len(itens_removidos) > 20:
                    msg += f"\n... e mais {len(itens_removidos) - 20} itens"
                
                QMessageBox.information(self, "Limpeza Concluída", msg)
            
            self.status_label.setText("Limpeza concluída.")
            
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao executar limpeza: {str(e)}")
            logger.error(f"Erro na limpeza 0200: {e}")
            self.lbl_clean_status.setText("Erro na limpeza")
            self.lbl_clean_status.setStyleSheet("color: red; font-weight: bold;")
    
    def _populate_validation_table(self, result: ValidationResult) -> None:
        """Preenche a tabela de resultados da validação."""
        self.table_validation.clearContents()
        
        issues = result.issues
        self.table_validation.setRowCount(len(issues))
        
        for i, issue in enumerate(issues):
            # Severidade
            severity_item = QTableWidgetItem(issue.severity.value)
            if issue.severity == Severity.ERROR:
                severity_item.setForeground(QColor(200, 0, 0))
                severity_item.setFont(QFont("", -1, QFont.Weight.Bold))
            elif issue.severity == Severity.WARNING:
                severity_item.setForeground(QColor(200, 128, 0))
            self.table_validation.setItem(i, 0, severity_item)
            
            # Código
            self.table_validation.setItem(i, 1, QTableWidgetItem(issue.code))
            
            # Registro
            self.table_validation.setItem(i, 2, QTableWidgetItem(issue.record))
            
            # Campo
            self.table_validation.setItem(i, 3, QTableWidgetItem(issue.field))
            
            # Mensagem
            self.table_validation.setItem(i, 4, QTableWidgetItem(issue.message))
        
        self.table_validation.resizeColumnsToContents()
    
    def setup_dashboard_tab(self) -> None:
        """Configura a aba Dashboard."""
        layout = QVBoxLayout(self.dashboard_w)
        
        # Título
        title = QLabel("Dashboard - Visão Geral do SPED")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # GroupBox - Informações do Arquivo
        grp_info = QGroupBox("Informações do Arquivo")
        grid_info = QGridLayout(grp_info)
        
        self.lbl_razao_social = QLabel("-")
        self.lbl_cnpj = QLabel("-")
        self.lbl_periodo = QLabel("-")
        self.lbl_total_registros = QLabel("-")
        
        grid_info.addWidget(QLabel("Razão Social:"), 0, 0)
        grid_info.addWidget(self.lbl_razao_social, 0, 1)
        grid_info.addWidget(QLabel("CNPJ:"), 0, 2)
        grid_info.addWidget(self.lbl_cnpj, 0, 3)
        grid_info.addWidget(QLabel("Período:"), 1, 0)
        grid_info.addWidget(self.lbl_periodo, 1, 1)
        grid_info.addWidget(QLabel("Total Registros:"), 1, 2)
        grid_info.addWidget(self.lbl_total_registros, 1, 3)
        
        layout.addWidget(grp_info)
        
        # GroupBox - Resumo Financeiro
        grp_finance = QGroupBox("Resumo Financeiro")
        grid_finance = QGridLayout(grp_finance)
        
        self.lbl_total_entradas = QLabel("R$ 0,00")
        self.lbl_total_saidas = QLabel("R$ 0,00")
        self.lbl_icms_entradas = QLabel("R$ 0,00")
        self.lbl_icms_saidas = QLabel("R$ 0,00")
        
        self.lbl_total_entradas.setStyleSheet("font-size: 14px; color: green; font-weight: bold;")
        self.lbl_total_saidas.setStyleSheet("font-size: 14px; color: red; font-weight: bold;")
        
        grid_finance.addWidget(QLabel("Total Entradas:"), 0, 0)
        grid_finance.addWidget(self.lbl_total_entradas, 0, 1)
        grid_finance.addWidget(QLabel("Total Saídas:"), 0, 2)
        grid_finance.addWidget(self.lbl_total_saidas, 0, 3)
        grid_finance.addWidget(QLabel("ICMS Entradas:"), 1, 0)
        grid_finance.addWidget(self.lbl_icms_entradas, 1, 1)
        grid_finance.addWidget(QLabel("ICMS Saídas:"), 1, 2)
        grid_finance.addWidget(self.lbl_icms_saidas, 1, 3)
        
        layout.addWidget(grp_finance)
        
        # GroupBox - Top CFOPs
        grp_cfops = QGroupBox("Top 5 CFOPs por Valor")
        grid_cfops = QGridLayout(grp_cfops)
        
        self.table_top_cfops = QTableWidget()
        self.table_top_cfops.setColumnCount(4)
        self.table_top_cfops.setHorizontalHeaderLabels(["CFOP", "Tipo", "Valor Total", "% do Total"])
        self.table_top_cfops.setMaximumHeight(200)
        grid_cfops.addWidget(self.table_top_cfops, 0, 0, 1, 4)
        
        layout.addWidget(grp_cfops)
        
        # GroupBox - Registros por Bloco
        grp_blocos = QGroupBox("Registros por Bloco")
        grid_blocos = QGridLayout(grp_blocos)
        
        self.lbl_blocos = QLabel("-")
        self.lbl_blocos.setWordWrap(True)
        grid_blocos.addWidget(self.lbl_blocos)
        
        layout.addWidget(grp_blocos)
        
        # GroupBox - Validações
        grp_valid = QGroupBox("Validações")
        grid_valid = QGridLayout(grp_valid)
        
        self.lbl_validacoes = QLabel("-")
        self.lbl_validacoes.setWordWrap(True)
        grid_valid.addWidget(self.lbl_validacoes)
        
        layout.addWidget(grp_valid)
        
        # Botão Atualizar
        btn_refresh = QPushButton("Atualizar Dashboard")
        btn_refresh.clicked.connect(self.refresh_dashboard)
        layout.addWidget(btn_refresh)
        
        layout.addStretch()
    
    def setup_search_tab(self) -> None:
        """Configura a aba de Busca Global."""
        layout = QVBoxLayout(self.search_w)
        
        # Título
        title = QLabel("Busca Global - Pesquisar em Todos os Registros")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        layout.addWidget(title)
        
        # Grupo de busca
        grp_search = QGroupBox("Parâmetros de Busca")
        grid_search = QGridLayout(grp_search)
        
        # Campo de busca
        self.txt_global_search = QLineEdit()
        self.txt_global_search.setPlaceholderText("Digite o termo para buscar (CNPJ, nota, produto, valor...)")
        self.txt_global_search.returnPressed.connect(self.execute_global_search)
        grid_search.addWidget(QLabel("Termo:"), 0, 0)
        grid_search.addWidget(self.txt_global_search, 0, 1, 1, 3)
        
        # Botão buscar
        btn_search = QPushButton("🔍 Buscar")
        btn_search.clicked.connect(self.execute_global_search)
        btn_search.setStyleSheet("font-weight: bold; padding: 5px 15px;")
        grid_search.addWidget(btn_search, 0, 4)
        
        # Botão buscar nota fiscal (C100 + C170)
        btn_search_invoice = QPushButton("📄 Buscar Nota Fiscal")
        btn_search_invoice.setToolTip("Busca nota fiscal e todos os seus itens (C100 + C170)")
        btn_search_invoice.clicked.connect(self.execute_invoice_search)
        btn_search_invoice.setStyleSheet("font-weight: bold; padding: 5px 15px; background-color: #e6f3ff;")
        grid_search.addWidget(btn_search_invoice, 0, 5)
        
        # Opções
        self.chk_case_sensitive = QCheckBox("Case sensitive")
        grid_search.addWidget(self.chk_case_sensitive, 1, 0)
        
        # Filtro por tipo de registro
        grid_search.addWidget(QLabel("Filtrar por registro:"), 1, 1)
        self.cmb_search_reg = QComboBox()
        self.cmb_search_reg.addItem("Todos os registros")
        self.cmb_search_reg.setMinimumWidth(150)
        grid_search.addWidget(self.cmb_search_reg, 1, 2)
        
        # Label de dica
        lbl_hint = QLabel("💡 Dica: Clique em 'Buscar Nota Fiscal' para ver C100 (documento) + C170 (itens) e editar")
        lbl_hint.setStyleSheet("color: #666; font-style: italic;")
        grid_search.addWidget(lbl_hint, 1, 3, 1, 3)
        
        layout.addWidget(grp_search)
        
        # Resultados
        grp_results = QGroupBox("Resultados da Busca")
        vbox_results = QVBoxLayout(grp_results)
        
        self.lbl_search_results = QLabel("Nenhuma busca realizada")
        self.lbl_search_results.setStyleSheet("font-weight: bold;")
        vbox_results.addWidget(self.lbl_search_results)
        
        # Tabela C100 (Documentos)
        vbox_results.addWidget(QLabel("📄 Documentos Fiscais (C100):"))
        self.table_c100 = QTableWidget()
        self.table_c100.setAlternatingRowColors(True)
        self.table_c100.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_c100.setMaximumHeight(200)
        self.table_c100.itemChanged.connect(self.on_search_result_cell_changed)
        vbox_results.addWidget(self.table_c100)
        
        # Tabela C170 (Itens)
        vbox_results.addWidget(QLabel("📦 Itens do Documento (C170):"))
        self.table_c170 = QTableWidget()
        self.table_c170.setAlternatingRowColors(True)
        self.table_c170.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_c170.itemChanged.connect(self.on_search_result_cell_changed)
        vbox_results.addWidget(self.table_c170)
        
        # Botões de ação
        hbox_actions = QHBoxLayout()
        
        btn_save_search = QPushButton("💾 Salvar Alterações")
        btn_save_search.setToolTip("Salva todas as edições feitas nos resultados")
        btn_save_search.clicked.connect(self.save_search_results)
        btn_save_search.setStyleSheet("font-weight: bold; padding: 5px;")
        hbox_actions.addWidget(btn_save_search)
        
        btn_refresh_search = QPushButton("🔄 Atualizar")
        btn_refresh_search.clicked.connect(self.execute_invoice_search)
        hbox_actions.addWidget(btn_refresh_search)
        
        hbox_actions.addStretch()
        vbox_results.addLayout(hbox_actions)
        
        layout.addWidget(grp_results)
        
        # Status
        hbox_status = QHBoxLayout()
        self.lbl_search_status = QLabel("Use 'Buscar Nota Fiscal' para ver C100 + C170 e editar")
        self.lbl_search_status.setStyleSheet("color: gray;")
        hbox_status.addWidget(self.lbl_search_status)
        
        btn_export_search = QPushButton("Exportar Resultados")
        btn_export_search.clicked.connect(self.export_search_results)
        hbox_status.addWidget(btn_export_search)
        
        layout.addLayout(hbox_status)
        
        self._last_search_results = pd.DataFrame()
    
    def execute_global_search(self) -> None:
        """Executa a busca global."""
        term = self.txt_global_search.text().strip()
        if not term:
            QMessageBox.warning(self, "Aviso", "Digite um termo para buscar.")
            return
        
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        self.status_label.setText(f"Buscando por '{term}'...")
        self.lbl_search_status.setText("Buscando...")
        
        # Obter filtro de registro
        reg_filter = None
        reg_text = self.cmb_search_reg.currentText()
        if reg_text != "Todos os registros":
            reg_filter = [reg_text.split(" ")[0]]
        
        # Executar busca
        results = self.manager.global_search(
            search_term=term,
            case_sensitive=self.chk_case_sensitive.isChecked(),
            reg_types=reg_filter
        )
        
        if results.empty:
            self.lbl_search_results.setText(f"Nenhum resultado encontrado para '{term}'")
            self.lbl_search_status.setText("Busca concluída - sem resultados")
            self.table_c100.clear()
            self.table_c100.setRowCount(0)
            self.table_c170.clear()
            self.table_c170.setRowCount(0)
        else:
            # Separar por tipo de registro
            c100_df = results[results['registro'] == 'C100'].copy() if 'registro' in results.columns else pd.DataFrame()
            c170_df = results[results['registro'] == 'C170'].copy() if 'registro' in results.columns else pd.DataFrame()
            
            # Para busca geral, colocar todos os resultados na tabela C100
            # (já que pode ter vários tipos de registro misturados)
            self._populate_table(self.table_c100, results, 'SEARCH', editable=False)
            self.table_c170.clear()
            self.table_c170.setRowCount(0)
            
            self.lbl_search_results.setText(
                f"Encontrados {len(results)} resultados para '{term}'"
            )
            self.lbl_search_status.setText(f"{len(results)} registros encontrados")
        
        self.status_label.setText("Busca concluída.")
    
    def execute_invoice_search(self) -> None:
        """Busca nota fiscal pelo número, retornando C100 e C170."""
        invoice_num = self.txt_global_search.text().strip()
        if not invoice_num:
            QMessageBox.warning(self, "Aviso", "Digite o número da nota fiscal.")
            return
        
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        self.status_label.setText(f"Buscando nota fiscal {invoice_num}...")
        self.lbl_search_status.setText("Buscando nota fiscal...")
        
        # Executar busca por nota fiscal
        c100_df, c170_df = self.manager.search_invoice(invoice_num)
        
        if c100_df.empty and c170_df.empty:
            self.lbl_search_results.setText(f"Nenhuma nota fiscal encontrada para '{invoice_num}'")
            self.lbl_search_status.setText("Busca concluída - sem resultados")
            self.table_c100.clear()
            self.table_c100.setRowCount(0)
            self.table_c170.clear()
            self.table_c170.setRowCount(0)
        else:
            c100_count = len(c100_df)
            c170_count = len(c170_df)
            
            self.lbl_search_results.setText(
                f"Nota {invoice_num}: {c100_count} documento(s) + {c170_count} itens"
            )
            
            # Preencher tabelas com colunas corretas para cada registro
            self._populate_table_c100(self.table_c100, c100_df)
            self._populate_table_c170(self.table_c170, c170_df)
            
            self.lbl_search_status.setText(
                f"Nota fiscal encontrada - C100: {c100_count} | C170: {c170_count} (editável)"
            )
        
        self.status_label.setText("Busca concluída.")
    
    def _populate_table(self, table: QTableWidget, df: pd.DataFrame, reg_type: str, editable: bool = False) -> None:
        """Preenche uma tabela com os dados do DataFrame."""
        table.clear()
        
        if df.empty:
            table.setRowCount(0)
            return
        
        # Remover colunas de controle
        skip_cols = ['registro', 'tipo_registro']
        cols = [c for c in df.columns if c not in skip_cols]
        
        # Colunas importantes primeiro
        priority_cols = ['id_row', 'parent_id', 'NUM_DOC', 'COD_ITEM', 'DESCR_ITEM', 
                        'QTD', 'VL_ITEM', 'CFOP', 'VL_DOC', 'VL_ICMS', 'CHV_NFE', 
                        'CNPJ', 'CST_ICMS', 'ALIQ_ICMS', 'VL_BC_ICMS', 'SER', 
                        'COD_MOD', 'DT_DOC', 'IND_OPER']
        
        display_cols = []
        for col in priority_cols:
            if col in cols and col not in display_cols:
                display_cols.append(col)
        
        # Adicionar outras colunas
        for col in cols:
            if col not in display_cols:
                display_cols.append(col)
        
        table.setColumnCount(len(display_cols))
        table.setRowCount(len(df))
        table.setHorizontalHeaderLabels(display_cols)
        table.setSortingEnabled(False)
        
        # Colunas editáveis
        editable_cols = ['VL_DOC', 'VL_ICMS', 'VL_BC_ICMS', 'QTD', 'VL_ITEM', 
                        'ALIQ_ICMS', 'DESCR_ITEM', 'DESCR_COMPL']
        
        for r in range(len(df)):
            row = df.iloc[r]
            for c, col_name in enumerate(display_cols):
                val = row[col_name]
                
                # Tratar NaN, None e valores numéricos
                if pd.isna(val) or val is None:
                    display_val = ""
                elif isinstance(val, float):
                    display_val = f"{val:,.2f}" if val != int(val) else str(int(val))
                else:
                    display_val = str(val)
                
                item = QTableWidgetItem(display_val)
                
                # Tornar célula editável se aplicável
                if col_name in editable_cols and editable:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                
                # Guardar metadados
                item.setData(Qt.ItemDataRole.UserRole, {
                    'row_idx': r,
                    'col_name': col_name,
                    'reg_type': reg_type,
                    'id_row': int(row['id_row']) if 'id_row' in row.index else 0
                })
                
                table.setItem(r, c, item)
        
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
    
    def _populate_table_c100(self, table: QTableWidget, df: pd.DataFrame) -> None:
        """Preenche tabela C100 com colunas corretas do registro."""
        table.clear()
        
        if df.empty:
            table.setRowCount(0)
            return
        
        # Colunas específicas do C100
        c100_cols = ['id_row', 'IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 
                     'COD_SIT', 'SER', 'NUM_DOC', 'CHV_NFE', 'DT_DOC', 'DT_E_S', 
                     'VL_DOC', 'IND_PGTO', 'VL_DESC', 'VL_ABAT_NT', 'VL_MERC', 
                     'IND_FRT', 'VL_FRT', 'VL_SEG', 'VL_OUT_DA', 'VL_BC_ICMS', 
                     'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_IPI', 
                     'VL_PIS', 'VL_COFINS', 'VL_PIS_ST', 'VL_COFINS_ST']
        
        # Filtrar colunas que existem no DataFrame
        display_cols = [c for c in c100_cols if c in df.columns]
        
        table.setColumnCount(len(display_cols))
        table.setRowCount(len(df))
        table.setHorizontalHeaderLabels(display_cols)
        table.setSortingEnabled(False)
        
        for r in range(len(df)):
            row = df.iloc[r]
            for c, col_name in enumerate(display_cols):
                val = row[col_name]
                
                if pd.isna(val) or val is None:
                    display_val = ""
                elif isinstance(val, float):
                    display_val = f"{val:,.2f}" if val != int(val) else str(int(val))
                else:
                    display_val = str(val)
                
                item = QTableWidgetItem(display_val)
                
                # Campos editáveis
                if col_name in ['VL_DOC', 'VL_ICMS', 'VL_BC_ICMS', 'VL_PIS', 'VL_COFINS']:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                
                item.setData(Qt.ItemDataRole.UserRole, {
                    'reg_type': 'C100',
                    'id_row': int(row['id_row']) if 'id_row' in row.index else 0
                })
                
                table.setItem(r, c, item)
        
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
    
    def _populate_table_c170(self, table: QTableWidget, df: pd.DataFrame) -> None:
        """Preenche tabela C170 com colunas corretas do registro."""
        table.clear()
        
        if df.empty:
            table.setRowCount(0)
            return
        
        # Colunas específicas do C170
        c170_cols = ['id_row', 'parent_id', 'NUM_ITEM', 'COD_ITEM', 'DESCR_COMPL', 
                     'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'IND_MOV', 'CST_ICMS', 
                     'CFOP', 'COD_NAT', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 
                     'VL_BC_ICMS_ST', 'ALIQ_ST', 'VL_ICMS_ST', 'IND_APUR', 
                     'CST_IPI', 'COD_ENQ', 'VL_BC_IPI', 'ALIQ_IPI', 'VL_IPI', 
                     'CST_PIS', 'VL_BC_PIS', 'ALIQ_PIS', 'VL_PIS', 
                     'CST_COFINS', 'VL_BC_COFINS', 'ALIQ_COFINS', 'VL_COFINS']
        
        # Filtrar colunas que existem no DataFrame
        display_cols = [c for c in c170_cols if c in df.columns]
        
        table.setColumnCount(len(display_cols))
        table.setRowCount(len(df))
        table.setHorizontalHeaderLabels(display_cols)
        table.setSortingEnabled(False)
        
        for r in range(len(df)):
            row = df.iloc[r]
            for c, col_name in enumerate(display_cols):
                val = row[col_name]
                
                if pd.isna(val) or val is None:
                    display_val = ""
                elif isinstance(val, float):
                    display_val = f"{val:,.2f}" if val != int(val) else str(int(val))
                else:
                    display_val = str(val)
                
                item = QTableWidgetItem(display_val)
                
                # Campos editáveis
                if col_name in ['QTD', 'VL_ITEM', 'VL_DESC', 'VL_BC_ICMS', 
                               'ALIQ_ICMS', 'VL_ICMS', 'DESCR_COMPL']:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                
                item.setData(Qt.ItemDataRole.UserRole, {
                    'reg_type': 'C170',
                    'id_row': int(row['id_row']) if 'id_row' in row.index else 0
                })
                
                table.setItem(r, c, item)
        
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
    
    def export_search_results(self) -> None:
        """Exporta os resultados da busca (C100 e C170)."""
        # Coletar dados das duas tabelas
        c100_data = self._table_to_dataframe(self.table_c100)
        c170_data = self._table_to_dataframe(self.table_c170)
        
        if c100_data.empty and c170_data.empty:
            QMessageBox.warning(self, "Aviso", "Nenhum resultado para exportar.")
            return
        
        fname, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar Resultados da Busca",
            "resultados_busca.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)"
        )
        
        if not fname:
            return
        
        try:
            if "CSV" in selected_filter:
                if not fname.endswith('.csv'):
                    fname += '.csv'
                # Concatenar para CSV
                combined = pd.concat([c100_data, c170_data], ignore_index=True)
                combined.to_csv(fname, index=False, encoding='utf-8-sig')
            else:
                if not fname.endswith('.xlsx'):
                    fname += '.xlsx'
                # Excel com duas abas
                with pd.ExcelWriter(fname, engine='openpyxl') as writer:
                    if not c100_data.empty:
                        c100_data.to_excel(writer, index=False, sheet_name='C100_Documentos')
                    if not c170_data.empty:
                        c170_data.to_excel(writer, index=False, sheet_name='C170_Itens')
            
            QMessageBox.information(
                self, "Sucesso",
                f"Resultados exportados com sucesso!\n{fname}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao exportar: {str(e)}")
    
    def _table_to_dataframe(self, table: QTableWidget) -> pd.DataFrame:
        """Converte uma QTableWidget para DataFrame."""
        if table.rowCount() == 0 or table.columnCount() == 0:
            return pd.DataFrame()
        
        cols = []
        for c in range(table.columnCount()):
            header = table.horizontalHeaderItem(c)
            if header:
                cols.append(header.text())
        
        data = []
        for r in range(table.rowCount()):
            row_data = {}
            for c, col_name in enumerate(cols):
                item = table.item(r, c)
                row_data[col_name] = item.text() if item else ""
            data.append(row_data)
        
        return pd.DataFrame(data)
    
    def on_search_result_cell_changed(self, item) -> None:
        """Evento quando uma célula da busca é editada."""
        # Marcar célula como modificada (borda indicando alteração)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    
    def save_search_results(self) -> None:
        """Salva todas as edições feitas nos resultados da busca."""
        saved_count = 0
        errors = []
        
        # Processar tabela C100
        c100_count, c100_errors = self._save_table(self.table_c100, 'C100')
        saved_count += c100_count
        errors.extend(c100_errors)
        
        # Processar tabela C170
        c170_count, c170_errors = self._save_table(self.table_c170, 'C170')
        saved_count += c170_count
        errors.extend(c170_errors)
        
        if saved_count > 0:
            QMessageBox.information(
                self, "Sucesso",
                f"{saved_count} campo(s) salvo(s) com sucesso!"
            )
            self.status_label.setText(f"{saved_count} campos salvos via busca global")
        elif not errors:
            QMessageBox.information(self, "Aviso", "Nenhuma alteração detectada.")
        
        if errors:
            QMessageBox.warning(
                self, "Aviso",
                f"Erros ao salvar: {', '.join(errors[:5])}"
            )
    
    def _save_table(self, table: QTableWidget, reg_type: str) -> tuple:
        """Salva alterações de uma tabela específica."""
        saved_count = 0
        errors = []
        
        # Encontrar coluna id_row
        id_col = -1
        for c in range(table.columnCount()):
            header = table.horizontalHeaderItem(c)
            if header and header.text() == 'id_row':
                id_col = c
                break
        
        if id_col < 0:
            return 0, []
        
        # Coletar todas as edições
        for r in range(table.rowCount()):
            id_item = table.item(r, id_col)
            if not id_item:
                continue
            
            try:
                row_id = int(id_item.text())
            except ValueError:
                continue
            
            # Verificar cada coluna
            for c in range(table.columnCount()):
                if c == id_col:
                    continue
                
                header = table.horizontalHeaderItem(c)
                if not header:
                    continue
                
                col_name = header.text()
                cell_item = table.item(r, c)
                
                if cell_item and cell_item.font().bold():
                    # Esta célula foi modificada (fonte negrita)
                    new_value = cell_item.text()
                    
                    # Salvar no banco
                    success = self.manager.save_changes(
                        reg_type, row_id, col_name, new_value, record_history=True
                    )
                    
                    if success:
                        saved_count += 1
                        # Remover negrita após salvar
                        font = cell_item.font()
                        font.setBold(False)
                        cell_item.setFont(font)
                    else:
                        errors.append(f"{reg_type}[{row_id}].{col_name}")
        
        return saved_count, errors
    
    def update_progress(self, val: int) -> None:
        """Atualiza barra de progresso."""
        self.progress.setValue(val)
    
    def import_sped(self) -> None:
        """Importa arquivo SPED."""
        fname, _ = QFileDialog.getOpenFileName(
            self, "Abrir SPED", "", "Texto (*.txt);;Todos (*.*)"
        )
        if fname:
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.status_label.setText("Importando...")
            try:
                regs = self.manager.import_file(fname, self.update_progress)
                self.populate_tree(regs)
                self.status_label.setText(f"Arquivo carregado: {os.path.basename(fname)}")
            except Exception as e:
                QMessageBox.critical(self, "Erro Fatal", str(e))
                logger.error(f"Erro ao importar: {e}")
            finally:
                self.progress.setVisible(False)
    
    def import_cte_xml(self) -> None:
        """Importa arquivo XML CTE e gera registros SPED da transportadora."""
        fname, _ = QFileDialog.getOpenFileName(
            self, "Abrir XML CTE", "", "XML (*.xml);;Todos (*.*)"
        )
        if fname:
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.status_label.setText("Importando CTE XML...")
            try:
                result = self.manager.import_cte_xml(fname)
                
                # Show result message
                status = result.get('status', 'error')
                message = result.get('message', 'Erro desconhecido')
                
                if status == 'already_exists':
                    QMessageBox.information(
                        self, "Transportadora Existente",
                        f"{message}\n\n"
                        f"Registro 0150: ID {result.get('0150_row_id')}\n"
                        f"COD_PART: {result.get('cod_part')}"
                    )
                else:
                    QMessageBox.information(
                        self, "Importação CTE Concluída",
                        f"{message}\n\n"
                        f"0150 ID: {result.get('0150_row_id')}\n"
                        f"D100 ID: {result.get('D100_row_id')}\n"
                        f"D190 ID: {result.get('D190_row_id')}\n"
                        f"Total D100 no bloco: {result.get('D100_count')}"
                    )
                
                # Atualizar árvore com os tipos de registro existentes no banco
                regs = self.manager.get_register_types()
                self.populate_tree(regs)
                
                # Recarregar dados atuais se houver registro selecionado
                if self.current_reg:
                    self.load_grid(self.current_reg)
                
                self.status_label.setText("Importação CTE concluída.")
                
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao importar CTE XML: {str(e)}")
                logger.error(f"Erro ao importar CTE XML: {e}")
            finally:
                self.progress.setVisible(False)
    
    def populate_tree(self, regs: List[str]) -> None:
        """Preenche a árvore de registros e atualiza filtros."""
        self.tree.clear()
        blocks: Dict[str, QTreeWidgetItem] = {}
        for r in regs:
            blk_char = r[0]
            if blk_char not in blocks:
                p = QTreeWidgetItem(self.tree)
                p.setText(0, f"Bloco {blk_char}")
                blocks[blk_char] = p
            count = self.manager.get_total_rows(r)
            child = QTreeWidgetItem(blocks[blk_char])
            child.setText(0, f"{r} ({count})")
            child.setData(0, Qt.ItemDataRole.UserRole, r)
        self.tree.expandAll()
        
        # Atualizar ComboBox de busca global
        self._update_search_reg_combo(regs)
    
    def _update_search_reg_combo(self, regs: List[str]) -> None:
        """Atualiza o ComboBox de filtro de registros na busca global."""
        self.cmb_search_reg.clear()
        self.cmb_search_reg.addItem("Todos os registros")
        for reg in regs:
            count = self.manager.get_total_rows(reg)
            self.cmb_search_reg.addItem(f"{reg} ({count})")
    
    def filter_tree(self, text: str) -> None:
        """Filtra a árvore de registros."""
        search = text.upper()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            block_item = root.child(i)
            block_visible = False
            for j in range(block_item.childCount()):
                child = block_item.child(j)
                txt = child.text(0).upper()
                if search in txt:
                    child.setHidden(False)
                    block_visible = True
                else:
                    child.setHidden(True)
            block_item.setHidden(not block_visible)
    
    def on_tree_click(self, item, col) -> None:
        """Evento de clique na árvore."""
        reg = item.data(0, Qt.ItemDataRole.UserRole)
        if reg:
            self.current_reg = reg
            self.current_page = 0
            self.load_grid(reg)
    
    def load_grid(self, reg: str) -> None:
        """Carrega dados na grade com paginação."""
        self.status_label.setText(f"Carregando {reg}...")
        self.table.blockSignals(True)
        self.table.clear()
        
        total_rows = self.manager.get_total_rows(reg)
        self.total_pages = max(1, (total_rows + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        
        df = self.manager.get_data(
            reg,
            limit=self.PAGE_SIZE,
            offset=self.current_page * self.PAGE_SIZE
        )
        
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.blockSignals(False)
            self.status_label.setText("Tabela vazia.")
            self.update_pagination_controls(total_rows)
            return
        
        cols = list(df.columns)
        self.table.setColumnCount(len(cols))
        self.table.setRowCount(len(df))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSortingEnabled(False)
        
        for r, row in df.iterrows():
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val) if val is not None else "")
                if cols[c] in ['id_row', 'parent_id']:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setBackground(Qt.GlobalColor.lightGray)
                self.table.setItem(r, c, item)
        
        self.lbl_info.setText(f"Editando: {reg} | Mostrando: {len(df)}/{total_rows}")
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self.update_pagination_controls(total_rows)
        self.status_label.setText("Pronto.")
    
    def update_pagination_controls(self, total_rows: int) -> None:
        """Atualiza controles de paginação."""
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < self.total_pages - 1)
        self.lbl_page.setText(f"Pagina {self.current_page + 1}/{self.total_pages}")
        self.lbl_total_rows.setText(f"Total: {total_rows} registros")
    
    def next_page(self) -> None:
        """Avança para próxima página."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            if self.current_reg:
                self.load_grid(self.current_reg)
    
    def prev_page(self) -> None:
        """Volta para página anterior."""
        if self.current_page > 0:
            self.current_page -= 1
            if self.current_reg:
                self.load_grid(self.current_reg)
    
    def on_cell_changed(self, item) -> None:
        """Evento de alteração de célula."""
        if not self.current_reg:
            return
        col_name = self.table.horizontalHeaderItem(item.column()).text()
        id_idx = -1
        for i in range(self.table.columnCount()):
            if self.table.horizontalHeaderItem(i).text() == 'id_row':
                id_idx = i
                break
        if id_idx != -1:
            row_id = self.table.item(item.row(), id_idx).text()
            if row_id:
                self.manager.save_changes(
                    self.current_reg,
                    int(row_id),
                    col_name,
                    item.text()
                )
    
    def fix_0200_action(self) -> None:
        """Ação de corrigir espaços no registro 0200."""
        self.status_label.setText("Limpando espacos do Registro 0200...")
        rows_affected, err = self.manager.fix_0200_spaces()
        if err:
            QMessageBox.warning(self, "Aviso", err)
        else:
            QMessageBox.information(
                self, "Sucesso",
                f"Espacos corrigidos!\nProdutos afetados: {rows_affected}"
            )
            if self.current_reg == '0200':
                self.load_grid('0200')
        self.status_label.setText("Pronto.")
    
    def fix_inventory_action(self) -> None:
        """Ação de ajustar inventário."""
        text, ok = QInputDialog.getText(
            self,
            "Ajustar Valor do Inventario",
            "Digite o novo valor TOTAL do Inventario (H005):"
        )
        
        if ok and text.strip():
            self.status_label.setText("Recalculando inventario...")
            
            success, msg = self.manager.adjust_inventory(text)
            
            if not success:
                QMessageBox.warning(self, "Aviso", msg)
            else:
                QMessageBox.information(self, "Sucesso", msg)
                if self.current_reg in ['H005', 'H010']:
                    self.load_grid(self.current_reg)
            
        self.status_label.setText("Pronto.")
    
    # ========================================================================
    # EXPORTAÇÃO EXCEL/CSV
    # ========================================================================
    def export_current_to_excel(self) -> None:
        """Exporta o registro atual para Excel."""
        if not self.current_reg:
            QMessageBox.warning(self, "Aviso", "Nenhum registro selecionado.")
            return
        
        fname, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar {self.current_reg} para Excel",
            f"SPED_{self.current_reg}.xlsx",
            "Excel (*.xlsx)"
        )
        
        if not fname:
            return
        
        if not fname.endswith('.xlsx'):
            fname += '.xlsx'
        
        self.status_label.setText(f"Exportando {self.current_reg}...")
        
        success, msg = export_to_excel(
            self.manager._conn,
            self.current_reg,
            fname
        )
        
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self._open_file(fname)
        else:
            QMessageBox.warning(self, "Aviso", msg)
        
        self.status_label.setText("Pronto.")
    
    def export_current_to_csv(self) -> None:
        """Exporta o registro atual para CSV."""
        if not self.current_reg:
            QMessageBox.warning(self, "Aviso", "Nenhum registro selecionado.")
            return
        
        fname, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar {self.current_reg} para CSV",
            f"SPED_{self.current_reg}.csv",
            "CSV (*.csv)"
        )
        
        if not fname:
            return
        
        if not fname.endswith('.csv'):
            fname += '.csv'
        
        self.status_label.setText(f"Exportando {self.current_reg}...")
        
        success, msg = export_to_csv(
            self.manager._conn,
            self.current_reg,
            fname
        )
        
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self._open_file(fname)
        else:
            QMessageBox.warning(self, "Aviso", msg)
        
        self.status_label.setText("Pronto.")
    
    def export_all_to_excel_action(self) -> None:
        """Exporta todos os registros para um único arquivo Excel."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        fname, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Todos os Registros para Excel",
            "SPED_Completo.xlsx",
            "Excel (*.xlsx)"
        )
        
        if not fname:
            return
        
        if not fname.endswith('.xlsx'):
            fname += '.xlsx'
        
        self.status_label.setText("Exportando todos os registros...")
        self.progress.setVisible(True)
        
        success, msg = export_all_to_excel(
            self.manager._conn,
            self.manager.structure,
            fname
        )
        
        self.progress.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Sucesso", msg)
            self._open_file(fname)
        else:
            QMessageBox.warning(self, "Aviso", msg)
        
        self.status_label.setText("Pronto.")
    
    def export_all_to_csv_action(self) -> None:
        """Exporta todos os registros para CSVs separados em uma pasta."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        output_dir = QFileDialog.getExistingDirectory(
            self, "Selecione pasta para salvar os CSVs"
        )
        
        if not output_dir:
            return
        
        self.status_label.setText("Exportando todos os registros...")
        self.progress.setVisible(True)
        
        success, msg = export_all_to_csv(
            self.manager._conn,
            self.manager.structure,
            output_dir
        )
        
        self.progress.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Sucesso", f"{msg}\nPasta: {output_dir}")
            self._open_file(output_dir)
        else:
            QMessageBox.warning(self, "Aviso", msg)
        
        self.status_label.setText("Pronto.")
    
    def run_sql(self) -> None:
        """Executa consulta SQL."""
        q = self.txt_sql.toPlainText()
        if not q:
            return
        result, err = self.manager.execute_sql(q)
        if err:
            QMessageBox.critical(self, "Erro SQL", err)
            return
        self.table_sql.clear()
        if isinstance(result, pd.DataFrame):
            self.table_sql.setColumnCount(len(result.columns))
            self.table_sql.setRowCount(len(result))
            self.table_sql.setHorizontalHeaderLabels(list(result.columns))
            self.table_sql.setSortingEnabled(False)
            for r, row in result.iterrows():
                for c, val in enumerate(row):
                    self.table_sql.setItem(r, c, QTableWidgetItem(str(val)))
            self.table_sql.setSortingEnabled(True)
        elif isinstance(result, str):
            self.table_sql.setRowCount(0)
            self.table_sql.setColumnCount(0)
            QMessageBox.information(self, "Sucesso", result)
            if self.current_reg:
                self.load_grid(self.current_reg)
    
    def show_cfop_summary(self) -> None:
        """Mostra resumo de CFOPs na aba de análise."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        try:
            data = process_sped_summary(self.manager.original_file)
            
            # Preencher tabela de entrada
            self.table_cfop_entrada.clear()
            self.table_cfop_entrada.setColumnCount(4)
            self.table_cfop_entrada.setHorizontalHeaderLabels(
                ["CFOP", "Valor Total", "Base ICMS", "Valor ICMS"]
            )
            self.table_cfop_entrada.setRowCount(len(data.cfop_entrada))
            
            row = 0
            for cfop in sorted(data.cfop_entrada.keys()):
                self.table_cfop_entrada.setItem(row, 0, QTableWidgetItem(cfop))
                self.table_cfop_entrada.setItem(
                    row, 1, QTableWidgetItem(f"R$ {data.cfop_entrada[cfop]:,.2f}")
                )
                self.table_cfop_entrada.setItem(
                    row, 2, QTableWidgetItem(f"R$ {data.icms_base_entrada[cfop]:,.2f}")
                )
                self.table_cfop_entrada.setItem(
                    row, 3, QTableWidgetItem(f"R$ {data.icms_value_entrada[cfop]:,.2f}")
                )
                row += 1
            
            # Preencher tabela de saída
            self.table_cfop_saida.clear()
            self.table_cfop_saida.setColumnCount(4)
            self.table_cfop_saida.setHorizontalHeaderLabels(
                ["CFOP", "Valor Total", "Base ICMS", "Valor ICMS"]
            )
            self.table_cfop_saida.setRowCount(len(data.cfop_saida))
            
            row = 0
            for cfop in sorted(data.cfop_saida.keys()):
                self.table_cfop_saida.setItem(row, 0, QTableWidgetItem(cfop))
                self.table_cfop_saida.setItem(
                    row, 1, QTableWidgetItem(f"R$ {data.cfop_saida[cfop]:,.2f}")
                )
                self.table_cfop_saida.setItem(
                    row, 2, QTableWidgetItem(f"R$ {data.icms_base_saida[cfop]:,.2f}")
                )
                self.table_cfop_saida.setItem(
                    row, 3, QTableWidgetItem(f"R$ {data.icms_value_saida[cfop]:,.2f}")
                )
                row += 1
            
            self.tabs.setCurrentWidget(self.cfop_w)
            self.status_label.setText("Resumo de CFOPs carregado.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao processar CFOPs: {str(e)}")
            logger.error(f"Erro ao mostrar resumo CFOP: {e}")
    
    def generate_cfop_reports(self) -> None:
        """Abre preview para relatórios detalhados por CFOP."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        show_pdf_preview(self.manager.original_file, "cfop", self)
    
    def export_sped(self) -> None:
        """Exporta arquivo SPED."""
        fname, _ = QFileDialog.getSaveFileName(
            self, "Salvar SPED", "Sped_Editado.txt", "Texto (*.txt)"
        )
        if fname:
            self.status_label.setText("Exportando...")
            try:
                txt = self.manager.generate_sped_string()
                with open(fname, 'w', encoding='latin-1') as f:
                    f.write(txt)
                QMessageBox.information(
                    self, "Sucesso",
                    "Arquivo exportado!\nBlocos foram recalculados."
                )
                self.status_label.setText("Exportacao concluida.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))
                logger.error(f"Erro ao exportar: {e}")
    
    def _open_file(self, path: str) -> None:
        """Abre arquivo/pasta no explorador."""
        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            logger.error(f"Nao foi possivel abrir {path}: {e}")
    
    # ========================================================================
    # UNDO / REDO
    # ========================================================================
    def undo_action(self) -> None:
        """Desfaz a última edição."""
        if self.manager.undo():
            self.update_history_status()
            if self.current_reg:
                self.load_grid(self.current_reg)
            self.status_label.setText("Edição desfeita.")
        else:
            self.status_label.setText("Nada para desfazer.")
    
    def redo_action(self) -> None:
        """Refaz a última edição desfeita."""
        if self.manager.redo():
            self.update_history_status()
            if self.current_reg:
                self.load_grid(self.current_reg)
            self.status_label.setText("Edição refeita.")
        else:
            self.status_label.setText("Nada para refazer.")
    
    def update_history_status(self) -> None:
        """Atualiza indicadores de undo/redo na status bar."""
        undo_count = self.manager.history.undo_count
        redo_count = self.manager.history.redo_count
        self.lbl_history.setText(f"Histórico: {undo_count} desfazer / {redo_count} refazer")
        self.undo_action_menu.setEnabled(undo_count > 0)
        self.redo_action_menu.setEnabled(redo_count > 0)
    
    # ========================================================================
    # DASHBOARD
    # ========================================================================
    def show_dashboard(self) -> None:
        """Mostra a aba Dashboard."""
        self.tabs.setCurrentWidget(self.dashboard_w)
        self.refresh_dashboard()
    
    def refresh_dashboard(self) -> None:
        """Atualiza os dados do Dashboard."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        self.status_label.setText("Carregando dashboard...")
        
        try:
            data = generate_dashboard_data(self.manager.original_file)
            self._populate_dashboard(data)
            self.status_label.setText("Dashboard atualizado.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao gerar dashboard: {str(e)}")
            logger.error(f"Erro ao gerar dashboard: {e}")
    
    def _populate_dashboard(self, data: DashboardData) -> None:
        """Preenche os widgets do Dashboard com os dados."""
        # Informações do arquivo
        self.lbl_razao_social.setText(data.razao_social or "-")
        self.lbl_cnpj.setText(data.cnpj or "-")
        
        if data.periodo_inicio and data.periodo_fim:
            self.lbl_periodo.setText(f"{data.periodo_inicio} a {data.periodo_fim}")
        else:
            self.lbl_periodo.setText("-")
        
        self.lbl_total_registros.setText(str(data.total_registros))
        
        # Resumo financeiro
        self.lbl_total_entradas.setText(f"R$ {data.total_entradas:,.2f}")
        self.lbl_total_saidas.setText(f"R$ {data.total_saidas:,.2f}")
        self.lbl_icms_entradas.setText(f"R$ {data.total_icms_entradas:,.2f}")
        self.lbl_icms_saidas.setText(f"R$ {data.total_icms_saidas:,.2f}")
        
        # Top CFOPs
        self.table_top_cfops.clearContents()
        all_cfops = []
        total_valor = data.total_entradas + data.total_saidas
        
        for cfop, valor in data.top_cfops_entrada[:5]:
            all_cfops.append((cfop, "Entrada", valor))
        for cfop, valor in data.top_cfops_saida[:5]:
            all_cfops.append((cfop, "Saída", valor))
        
        # Ordenar por valor e pegar top 5
        all_cfops.sort(key=lambda x: x[2], reverse=True)
        all_cfops = all_cfops[:5]
        
        self.table_top_cfops.setRowCount(len(all_cfops))
        for i, (cfop, tipo, valor) in enumerate(all_cfops):
            self.table_top_cfops.setItem(i, 0, QTableWidgetItem(cfop))
            item_tipo = QTableWidgetItem(tipo)
            if tipo == "Entrada":
                item_tipo.setForeground(QColor(0, 128, 0))
            else:
                item_tipo.setForeground(QColor(255, 0, 0))
            self.table_top_cfops.setItem(i, 1, item_tipo)
            self.table_top_cfops.setItem(i, 2, QTableWidgetItem(f"R$ {valor:,.2f}"))
            pct = (valor / total_valor * 100) if total_valor > 0 else 0
            self.table_top_cfops.setItem(i, 3, QTableWidgetItem(f"{pct:.1f}%"))
        
        # Registros por bloco
        blocos_texto = ""
        for bloco, qtd in sorted(data.registros_por_bloco.items()):
            nome_bloco = {
                '0': 'Abertura/Identificação',
                'C': 'Documentos Fiscais I',
                'D': 'Documentos Fiscais II',
                'E': 'Apuração do ICMS',
                'H': 'Inventário Físico',
                '1': 'Complemento',
                '9': 'Controle/Encerramento'
            }.get(bloco, f'Bloco {bloco}')
            blocos_texto += f"Bloco {bloco} ({nome_bloco}): {qtd} registros\n"
        self.lbl_blocos.setText(blocos_texto.strip() if blocos_texto else "-")
        
        # Validações
        if data.erros_validacao:
            self.lbl_validacoes.setText("\n".join(data.erros_validacao))
            self.lbl_validacoes.setStyleSheet("color: red;")
        else:
            self.lbl_validacoes.setText("✓ Arquivo válido - nenhuma inconsistência encontrada")
            self.lbl_validacoes.setStyleSheet("color: green;")
    
    # ========================================================================
    # RELATÓRIOS CONSOLIDADOS
    # ========================================================================
    def generate_entrada_report(self) -> None:
        """Gera relatório consolidado de todas as entradas."""
        self._generate_consolidated_report("entrada", "Entradas")
    
    def generate_saida_report(self) -> None:
        """Gera relatório consolidado de todas as saídas."""
        self._generate_consolidated_report("saida", "Saídas")
    
    def generate_all_reports(self) -> None:
        """Gera relatórios consolidados de entradas e saídas."""
        self._generate_consolidated_report("todos", "Entradas e Saídas")
    
    def _generate_consolidated_report(self, report_type: str, label: str) -> None:
        """Abre preview para relatório consolidado do tipo especificado."""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        show_pdf_preview(self.manager.original_file, report_type, self)
        
        self.status_label.setText("Pronto.")
