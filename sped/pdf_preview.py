"""
Módulo de pré-visualização de PDF do SPED Fiscal.
Contém a janela de preview com opções de retrato/paisagem.
"""

import os
import logging
from typing import List, Optional, Dict, Any
from collections import defaultdict, OrderedDict

from fpdf import FPDF
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QGroupBox, QWidget,
                             QMessageBox, QFileDialog, QTextEdit, QSplitter)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .models import SpedRecord, ENTRADA_CFOPS_PREFIX
from .parser import process_sped_detailed

logger = logging.getLogger(__name__)


class PDFPreviewDialog(QDialog):
    """Diálogo de pré-visualização de PDF com opções de retrato/paisagem."""
    
    def __init__(self, original_file: str, report_type: str, parent=None):
        super().__init__(parent)
        self.original_file = original_file
        self.report_type = report_type
        self.cfop = None
        self.current_config = {}
        self.preview_data = None
        
        self.setWindowTitle("Pré-visualização do Relatório PDF")
        self.setMinimumSize(950, 700)
        self.resize(1000, 750)
        
        self.setup_ui()
        self.load_preview_data()
        self.update_preview()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Grupo de configurações
        grp_config = QGroupBox("Configurações do Relatório")
        config_layout = QHBoxLayout(grp_config)
        
        config_layout.addWidget(QLabel("Orientação:"))
        self.combo_orientation = QComboBox()
        self.combo_orientation.addItems(["Paisagem", "Retrato"])
        self.combo_orientation.currentIndexChanged.connect(self.update_preview)
        config_layout.addWidget(self.combo_orientation)
        
        config_layout.addWidget(QLabel("Tamanho da Fonte:"))
        self.combo_font_size = QComboBox()
        self.combo_font_size.addItems(["7", "8", "9", "10", "11", "12"])
        self.combo_font_size.setCurrentText("9")
        self.combo_font_size.currentIndexChanged.connect(self.update_preview)
        config_layout.addWidget(self.combo_font_size)
        
        config_layout.addStretch()
        layout.addWidget(grp_config)
        
        # Splitter para preview
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Área de preview textual
        grp_preview = QGroupBox("Visualização do Relatório")
        preview_layout = QVBoxLayout(grp_preview)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFont(QFont("Courier New", 9))
        self.preview_text.setStyleSheet("background-color: white; color: black;")
        preview_layout.addWidget(self.preview_text)
        
        splitter.addWidget(grp_preview)
        
        # Resumo
        grp_summary = QGroupBox("Resumo")
        summary_layout = QVBoxLayout(grp_summary)
        
        self.summary_label = QLabel()
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary_layout.addWidget(self.summary_label)
        
        splitter.addWidget(grp_summary)
        splitter.setSizes([500, 150])
        
        layout.addWidget(splitter, stretch=1)
        
        # Botões
        btn_layout = QHBoxLayout()
        
        btn_refresh = QPushButton("Atualizar Preview")
        btn_refresh.clicked.connect(self.update_preview)
        btn_layout.addWidget(btn_refresh)
        
        btn_layout.addStretch()
        
        btn_export = QPushButton("Exportar PDF")
        btn_export.setStyleSheet("font-weight: bold; padding: 10px 20px; background-color: #90EE90;")
        btn_export.clicked.connect(self.export_pdf)
        btn_layout.addWidget(btn_export)
        
        btn_close = QPushButton("Fechar")
        btn_close.setStyleSheet("padding: 10px 20px;")
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)
    
    def set_cfop(self, cfop: str):
        self.cfop = cfop
    
    def load_preview_data(self):
        """Carrega os dados do SPED para preview."""
        try:
            self.preview_data = process_sped_detailed(self.original_file)
        except Exception as e:
            logger.error(f"Erro ao carregar dados: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao carregar dados: {str(e)}")
    
    def update_preview(self):
        """Atualiza o preview com base nas configurações atuais."""
        if not self.preview_data:
            self.preview_text.setText("Erro: Dados não carregados")
            return
        
        orientation = self.combo_orientation.currentText()
        font_size = int(self.combo_font_size.currentText())
        is_landscape = orientation == "Paisagem"
        
        # Construir texto do preview
        lines = []
        lines.append("=" * 80)
        lines.append(f"RELATÓRIO SPED FISCAL")
        lines.append(f"Orientação: {orientation} | Fonte: {font_size}pt")
        lines.append("=" * 80)
        lines.append("")
        
        all_records = []
        
        if self.report_type == "cfop_unico" and self.cfop:
            records = self.preview_data.get(self.cfop, [])
            all_records = records
            lines.append(f"CFOP {self.cfop} - {len(records)} registro(s)")
            lines.append("-" * 80)
            lines.extend(self._format_table(records, is_landscape, font_size))
            
        elif self.report_type == "cfop":
            for cfop in sorted(self.preview_data.keys())[:1]:
                records = self.preview_data[cfop]
                all_records = records
                lines.append(f"CFOP {cfop} - {len(records)} registro(s)")
                lines.append("-" * 80)
                lines.extend(self._format_table(records, is_landscape, font_size))
                
        elif self.report_type == "entrada":
            filtered = {c: r for c, r in self.preview_data.items() 
                       if c.startswith(ENTRADA_CFOPS_PREFIX)}
            for records in filtered.values():
                all_records.extend(records)
            lines.append(f"RELATÓRIO CONSOLIDADO - ENTRADAS")
            lines.append(f"CFOPs: {len(filtered)} | Total registros: {len(all_records)}")
            lines.append("-" * 80)
            for cfop in sorted(filtered.keys()):
                records = filtered[cfop]
                lines.append(f"\nCFOP {cfop} ({len(records)} registros)")
                lines.extend(self._format_table(records, is_landscape, font_size))
                
        elif self.report_type == "saida":
            filtered = {c: r for c, r in self.preview_data.items() 
                       if not c.startswith(ENTRADA_CFOPS_PREFIX)}
            for records in filtered.values():
                all_records.extend(records)
            lines.append(f"RELATÓRIO CONSOLIDADO - SAÍDAS")
            lines.append(f"CFOPs: {len(filtered)} | Total registros: {len(all_records)}")
            lines.append("-" * 80)
            for cfop in sorted(filtered.keys()):
                records = filtered[cfop]
                lines.append(f"\nCFOP {cfop} ({len(records)} registros)")
                lines.extend(self._format_table(records, is_landscape, font_size))
                
        else:  # todos
            for records in self.preview_data.values():
                all_records.extend(records)
            lines.append(f"RELATÓRIO CONSOLIDADO - ENTRADAS + SAÍDAS")
            lines.append(f"CFOPs: {len(self.preview_data)} | Total registros: {len(all_records)}")
            lines.append("-" * 80)
            for cfop in sorted(self.preview_data.keys()):
                records = self.preview_data[cfop]
                lines.append(f"\nCFOP {cfop} ({len(records)} registros)")
                lines.extend(self._format_table(records, is_landscape, font_size))
        
        self.preview_text.setPlainText("\n".join(lines))
        
        # Atualizar resumo
        if all_records:
            total_valor = sum(r.valor_operacao for r in all_records)
            total_icms = sum(r.valor_icms for r in all_records)
            total_base = sum(r.base_icms for r in all_records)
            
            summary = f"""
            <b>Resumo do Relatório:</b><br>
            <table style="margin: 10px;">
                <tr><td><b>Total de Registros:</b></td><td>{len(all_records)}</td></tr>
                <tr><td><b>Valor Total Operação:</b></td><td>R$ {total_valor:,.2f}</td></tr>
                <tr><td><b>Base Total ICMS:</b></td><td>R$ {total_base:,.2f}</td></tr>
                <tr><td><b>Valor Total ICMS:</b></td><td>R$ {total_icms:,.2f}</td></tr>
                <tr><td><b>Orientação:</b></td><td>{orientation}</td></tr>
                <tr><td><b>Formato:</b></td><td>A4</td></tr>
            </table>
            """
            self.summary_label.setText(summary)
        else:
            self.summary_label.setText("<b>Nenhum registro encontrado</b>")
    
    def _format_table(self, records: List[SpedRecord], is_landscape: bool, font_size: int) -> List[str]:
        """Formata os registros como tabela de texto."""
        lines = []
        
        # Agrupar por (numero_doc, aliquota)
        grouped = OrderedDict()
        for record in records:
            key = (record.numero_doc, record.aliquota)
            if key not in grouped:
                grouped[key] = {
                    'cfop': record.cfop,
                    'numero_doc': record.numero_doc,
                    'aliquota': record.aliquota,
                    'valor_operacao': 0.0,
                    'base_icms': 0.0,
                    'valor_icms': 0.0
                }
            grouped[key]['valor_operacao'] += record.valor_operacao
            grouped[key]['base_icms'] += record.base_icms
            grouped[key]['valor_icms'] += record.valor_icms
        
        # Cabeçalho
        if is_landscape:
            header = f"{'CFOP':<8}{'Nota':<15}{'Valor Operação':>20}{'Base ICMS':>20}{'Alíq.':>10}{'Valor ICMS':>20}"
            separator = "-" * 93
        else:
            header = f"{'CFOP':<8}{'Nota':<12}{'Valor Oper.':>15}{'Base ICMS':>15}{'Alíq.':>8}{'Valor ICMS':>15}"
            separator = "-" * 73
        
        lines.append(header)
        lines.append(separator)
        
        totals = defaultdict(float)
        
        for key, data in grouped.items():
            if is_landscape:
                line = (f"{data['cfop']:<8}"
                       f"{str(data['numero_doc']):<15}"
                       f"R$ {data['valor_operacao']:>15,.2f}"
                       f"R$ {data['base_icms']:>15,.2f}"
                       f"{data['aliquota']:>8.1f}%"
                       f"R$ {data['valor_icms']:>15,.2f}")
            else:
                line = (f"{data['cfop']:<8}"
                       f"{str(data['numero_doc']):<12}"
                       f"R$ {data['valor_operacao']:>12,.2f}"
                       f"R$ {data['base_icms']:>12,.2f}"
                       f"{data['aliquota']:>6.1f}%"
                       f"R$ {data['valor_icms']:>12,.2f}")
            
            lines.append(line)
            
            totals['valor_operacao'] += data['valor_operacao']
            totals['base_icms'] += data['base_icms']
            totals['valor_icms'] += data['valor_icms']
        
        lines.append(separator)
        
        if is_landscape:
            total_line = (f"{'TOTAIS':<23}"
                         f"R$ {totals['valor_operacao']:>15,.2f}"
                         f"R$ {totals['base_icms']:>15,.2f}"
                         f"{'':>10}"
                         f"R$ {totals['valor_icms']:>15,.2f}")
        else:
            total_line = (f"{'TOTAIS':<20}"
                         f"R$ {totals['valor_operacao']:>12,.2f}"
                         f"R$ {totals['base_icms']:>12,.2f}"
                         f"{'':>8}"
                         f"R$ {totals['valor_icms']:>12,.2f}")
        
        lines.append(total_line)
        
        return lines
    
    def export_pdf(self):
        """Exporta o PDF com as configurações atuais."""
        if not self.preview_data:
            QMessageBox.warning(self, "Aviso", "Nenhum dado para exportar.")
            return
        
        orientation = 'L' if self.combo_orientation.currentText() == "Paisagem" else 'P'
        font_size = int(self.combo_font_size.currentText())
        
        # Para "cfop": gerar um PDF por CFOP
        if self.report_type == "cfop":
            output_dir = QFileDialog.getExistingDirectory(
                self, "Selecione pasta para salvar os PDFs"
            )
            if not output_dir:
                return
            
            try:
                count = 0
                for cfop in sorted(self.preview_data.keys()):
                    records = self.preview_data[cfop]
                    if records:
                        pdf = FPDF(orientation=orientation, format='A4')
                        pdf.set_auto_page_break(auto=True, margin=15)
                        pdf.add_page()
                        
                        pdf.set_font("Arial", 'B', min(14, font_size + 4))
                        pdf.cell(0, 10, f"Relatório Detalhado - CFOP {cfop}", ln=True, align='C')
                        pdf.set_font("Arial", '', min(10, font_size))
                        pdf.cell(0, 8, f"Total de Registros: {len(records)}", ln=True, align='C')
                        pdf.ln(5)
                        
                        self._draw_pdf_table(pdf, records, orientation, font_size)
                        
                        pdf_path = os.path.join(output_dir, f"relatorio_CFOP_{cfop}.pdf")
                        pdf.output(pdf_path)
                        count += 1
                
                QMessageBox.information(
                    self, "Sucesso", 
                    f"{count} PDFs gerados com sucesso!\nPasta: {output_dir}"
                )
                
            except Exception as e:
                logger.error(f"Erro ao exportar PDFs: {e}")
                QMessageBox.critical(self, "Erro", f"Erro ao exportar: {str(e)}")
        
        else:
            # Para outros tipos: salvar em um único arquivo
            default_name = "relatorio_sped.pdf"
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Salvar Relatório PDF", default_name,
                "PDF Files (*.pdf);;All Files (*)"
            )
            
            if not file_path:
                return
            
            try:
                # Obter registros filtrados
                dados_filtrados = self._get_filtered_data()
                
                # Gerar PDF
                pdf = FPDF(orientation=orientation, format='A4')
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                
                # Título
                pdf.set_font("Arial", 'B', min(16, font_size + 6))
                titulo = self._get_title()
                pdf.cell(0, 12, titulo, ln=True, align='C')
                pdf.ln(5)
                
                # Resumo
                all_records = []
                for records in dados_filtrados.values():
                    all_records.extend(records)
                
                if all_records:
                    pdf.set_font("Arial", '', min(10, font_size))
                    pdf.cell(0, 8, f"Total de Registros: {len(all_records)}", ln=True, align='C')
                    pdf.cell(0, 8, f"CFOPs Incluídos: {len(dados_filtrados)}", ln=True, align='C')
                    total_valor = sum(r.valor_operacao for r in all_records)
                    total_icms = sum(r.valor_icms for r in all_records)
                    pdf.cell(0, 8, f"Valor Total: R$ {total_valor:,.2f} | ICMS Total: R$ {total_icms:,.2f}", 
                            ln=True, align='C')
                
                pdf.ln(10)
                
                # Detalhamento por CFOP
                for cfop in sorted(dados_filtrados.keys()):
                    records = dados_filtrados[cfop]
                    if records:
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', min(12, font_size + 2))
                        pdf.cell(0, 10, f"CFOP {cfop} - {len(records)} registros", ln=True, align='C')
                        pdf.ln(3)
                        self._draw_pdf_table(pdf, records, orientation, font_size)
                
                # Salvar
                pdf.output(file_path)
                
                QMessageBox.information(
                    self, "Sucesso", 
                    f"Relatório exportado com sucesso!\n\n{file_path}"
                )
                
            except Exception as e:
                logger.error(f"Erro ao exportar PDF: {e}")
                QMessageBox.critical(self, "Erro", f"Erro ao exportar: {str(e)}")
    
    def _get_filtered_data(self) -> Dict[str, List[SpedRecord]]:
        """Retorna dados filtrados baseado no tipo de relatório."""
        if self.report_type == "entrada":
            # Filtrar apenas CFOPs de entrada (1xxx, 2xxx, 3xxx)
            return {c: r for c, r in self.preview_data.items() 
                   if c.startswith(ENTRADA_CFOPS_PREFIX)}
        elif self.report_type == "saida":
            # Filtrar apenas CFOPs de saída (5xxx, 6xxx, 7xxx)
            return {c: r for c, r in self.preview_data.items() 
                   if not c.startswith(ENTRADA_CFOPS_PREFIX)}
        else:  # todos
            return self.preview_data
    
    def _get_title(self) -> str:
        """Retorna o título do relatório."""
        titulos = {
            "cfop": "Relatório por CFOP",
            "cfop_unico": f"Relatório CFOP {self.cfop}",
            "entrada": "Relatório Consolidado - Entradas",
            "saida": "Relatório Consolidado - Saídas",
            "todos": "Relatório Consolidado - Entradas + Saídas"
        }
        return titulos.get(self.report_type, "Relatório SPED")
    
    def _draw_pdf_table(self, pdf: FPDF, records: List[SpedRecord], 
                        orientation: str, font_size: int):
        """Desenha tabela no PDF."""
        # Agrupar
        grouped = OrderedDict()
        for record in records:
            key = (record.numero_doc, record.aliquota)
            if key not in grouped:
                grouped[key] = {
                    'cfop': record.cfop,
                    'numero_doc': record.numero_doc,
                    'aliquota': record.aliquota,
                    'valor_operacao': 0.0,
                    'base_icms': 0.0,
                    'valor_icms': 0.0
                }
            grouped[key]['valor_operacao'] += record.valor_operacao
            grouped[key]['base_icms'] += record.base_icms
            grouped[key]['valor_icms'] += record.valor_icms
        
        # Colunas
        if orientation == 'L':
            headers = ["CFOP", "Nota Fiscal", "Valor Operação", "Base ICMS", "Alíquota", "Valor ICMS"]
            col_widths = [25, 35, 45, 45, 25, 45]
        else:
            headers = ["CFOP", "Nota", "Valor Oper.", "Base ICMS", "Alíq.", "Valor ICMS"]
            col_widths = [18, 25, 32, 32, 18, 32]
        
        # Cabeçalho
        pdf.set_font("Arial", 'B', font_size)
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, border=1, align='C')
        pdf.ln()
        
        # Dados
        pdf.set_font("Arial", '', max(7, font_size - 1))
        totals = defaultdict(float)
        
        for key, data in grouped.items():
            pdf.cell(col_widths[0], 7, data['cfop'], border=1)
            pdf.cell(col_widths[1], 7, str(data['numero_doc']), border=1)
            pdf.cell(col_widths[2], 7, f"R$ {data['valor_operacao']:,.2f}", border=1, align='R')
            pdf.cell(col_widths[3], 7, f"R$ {data['base_icms']:,.2f}", border=1, align='R')
            pdf.cell(col_widths[4], 7, f"{data['aliquota']:.1f}%", border=1, align='C')
            pdf.cell(col_widths[5], 7, f"R$ {data['valor_icms']:,.2f}", border=1, align='R')
            pdf.ln()
            
            totals['valor_operacao'] += data['valor_operacao']
            totals['base_icms'] += data['base_icms']
            totals['valor_icms'] += data['valor_icms']
        
        # Totais
        pdf.set_font("Arial", 'B', font_size)
        pdf.cell(col_widths[0] + col_widths[1], 8, "TOTAIS", border=1, align='C')
        pdf.cell(col_widths[2], 8, f"R$ {totals['valor_operacao']:,.2f}", border=1, align='R')
        pdf.cell(col_widths[3], 8, f"R$ {totals['base_icms']:,.2f}", border=1, align='R')
        pdf.cell(col_widths[4], 8, "", border=1)
        pdf.cell(col_widths[5], 8, f"R$ {totals['valor_icms']:,.2f}", border=1, align='R')


def show_pdf_preview(original_file: str, report_type: str, parent=None, cfop: str = None):
    """Mostra o diálogo de preview."""
    dialog = PDFPreviewDialog(original_file, report_type, parent)
    if cfop:
        dialog.set_cfop(cfop)
    dialog.exec()
