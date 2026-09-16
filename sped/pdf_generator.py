"""
Módulo de geração de PDF do SPED Fiscal.
Contém funções para criar relatórios em PDF.
"""

import os
import logging
from typing import List, Tuple, Literal
from collections import defaultdict

from fpdf import FPDF

from .models import SpedRecord, ENTRADA_CFOPS_PREFIX
from .parser import process_sped_detailed

logger = logging.getLogger(__name__)


def generate_cfop_analysis_pdf(original_file: str, output_dir: str) -> Tuple[int, str]:
    """
    Gera PDFs detalhados por CFOP (um PDF para cada CFOP).
    
    Args:
        original_file: Caminho do arquivo SPED original
        output_dir: Diretório de saída para os PDFs
    
    Returns:
        Tuple com (quantidade de PDFs gerados, mensagem)
    """
    try:
        if not original_file:
            return 0, "Nenhum arquivo foi carregado."
        
        dados_por_cfop = process_sped_detailed(original_file)
        count = 0
        
        for cfop, records in sorted(dados_por_cfop.items()):
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page(orientation='L')
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, f"Relatório Detalhado - CFOP {cfop}", ln=True, align='C')
            pdf.ln(10)
            _draw_pdf_table(pdf, records)
            
            pdf_path = os.path.join(output_dir, f"relatorio_CFOP_{cfop}.pdf")
            pdf.output(pdf_path)
            count += 1
            logger.info(f"PDF gerado para CFOP {cfop}: {pdf_path}")
        
        return count, f"Sucesso ao gerar {count} PDFs por CFOP"
    except Exception as e:
        logger.error(f"Erro ao gerar PDFs por CFOP: {e}")
        return 0, f"Erro: {str(e)}"


def generate_consolidated_pdf(
    original_file: str, 
    output_dir: str, 
    report_type: Literal["entrada", "saida", "todos"]
) -> Tuple[int, str]:
    """
    Gera PDFs consolidados agrupados por tipo (entrada/saída).
    
    Args:
        original_file: Caminho do arquivo SPED original
        output_dir: Diretório de saída para os PDFs
        report_type: Tipo de relatório ("entrada", "saida" ou "todos")
    
    Returns:
        Tuple com (quantidade de PDFs gerados, mensagem)
    """
    try:
        if not original_file:
            return 0, "Nenhum arquivo foi carregado."
        
        dados_por_cfop = process_sped_detailed(original_file)
        
        if report_type == "entrada":
            # Filtrar apenas CFOPs de entrada
            filtered = {
                cfop: records for cfop, records in dados_por_cfop.items()
                if cfop.startswith(ENTRADA_CFOPS_PREFIX)
            }
            filename = "relatorio_Entradas_Todos_CFOPs.pdf"
            title = "Relatório Consolidado - Todas as Entradas"
            count = _generate_single_consolidated_pdf(filtered, output_dir, filename, title)
            return count, f"Sucesso ao gerar relatório de entradas ({count} registros)"
            
        elif report_type == "saida":
            # Filtrar apenas CFOPs de saída
            filtered = {
                cfop: records for cfop, records in dados_por_cfop.items()
                if not cfop.startswith(ENTRADA_CFOPS_PREFIX)
            }
            filename = "relatorio_Saidas_Todos_CFOPs.pdf"
            title = "Relatório Consolidado - Todas as Saídas"
            count = _generate_single_consolidated_pdf(filtered, output_dir, filename, title)
            return count, f"Sucesso ao gerar relatório de saídas ({count} registros)"
            
        else:  # todos
            # Gerar dois relatórios: um de entrada e um de saída
            count = 0
            
            entradas = {
                cfop: records for cfop, records in dados_por_cfop.items()
                if cfop.startswith(ENTRADA_CFOPS_PREFIX)
            }
            if entradas:
                c, _ = _generate_single_consolidated_pdf(
                    entradas, output_dir, 
                    "relatorio_Entradas_Todos_CFOPs.pdf",
                    "Relatório Consolidado - Todas as Entradas"
                )
                count += c
            
            saidas = {
                cfop: records for cfop, records in dados_por_cfop.items()
                if not cfop.startswith(ENTRADA_CFOPS_PREFIX)
            }
            if saidas:
                c, _ = _generate_single_consolidated_pdf(
                    saidas, output_dir,
                    "relatorio_Saidas_Todos_CFOPs.pdf", 
                    "Relatório Consolidado - Todas as Saídas"
                )
                count += c
            
            return count, f"Sucesso ao gerar {count} relatórios consolidados"
        
    except Exception as e:
        logger.error(f"Erro ao gerar PDF consolidado: {e}")
        return 0, f"Erro: {str(e)}"


def _generate_single_consolidated_pdf(
    dados_por_cfop: dict,
    output_dir: str,
    filename: str,
    title: str
) -> int:
    """
    Gera um único PDF consolidado com todos os CFOPs fornecidos.
    
    Args:
        dados_por_cfop: Dicionário {cfop: [SpedRecord, ...]}
        output_dir: Diretório de saída
        filename: Nome do arquivo PDF
        title: Título do relatório
    
    Returns:
        Quantidade de registros incluídos
    """
    all_records = []
    for cfop in sorted(dados_por_cfop.keys()):
        all_records.extend(dados_por_cfop[cfop])
    
    if not all_records:
        return 0
    
    pdf = FPDF(orientation='L', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Página de capa
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20)
    pdf.ln(40)
    pdf.cell(0, 15, title, ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Total de Registros: {len(all_records)}", ln=True, align='C')
    pdf.cell(0, 10, f"CFOPs Incluídos: {len(dados_por_cfop)}", ln=True, align='C')
    
    # Calcular totais
    total_valor = sum(r.valor_operacao for r in all_records)
    total_icms = sum(r.valor_icms for r in all_records)
    pdf.cell(0, 10, f"Valor Total das Operações: R$ {total_valor:,.2f}", ln=True, align='C')
    pdf.cell(0, 10, f"Valor Total do ICMS: R$ {total_icms:,.2f}", ln=True, align='C')
    
    # Resumo por CFOP
    pdf.ln(20)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Resumo por CFOP:", ln=True, align='L')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(50, 8, "CFOP", border=1, align='C')
    pdf.cell(30, 8, "Qtd Notas", border=1, align='C')
    pdf.cell(50, 8, "Valor Total", border=1, align='C')
    pdf.cell(50, 8, "Base ICMS", border=1, align='C')
    pdf.cell(50, 8, "Valor ICMS", border=1, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    cfop_summary = defaultdict(lambda: {"count": 0, "valor": 0.0, "base": 0.0, "icms": 0.0})
    for r in all_records:
        cfop_summary[r.cfop]["count"] += 1
        cfop_summary[r.cfop]["valor"] += r.valor_operacao
        cfop_summary[r.cfop]["base"] += r.base_icms
        cfop_summary[r.cfop]["icms"] += r.valor_icms
    
    for cfop in sorted(cfop_summary.keys()):
        s = cfop_summary[cfop]
        pdf.cell(50, 8, cfop, border=1, align='C')
        pdf.cell(30, 8, str(s["count"]), border=1, align='C')
        pdf.cell(50, 8, f"R$ {s['valor']:,.2f}", border=1, align='R')
        pdf.cell(50, 8, f"R$ {s['base']:,.2f}", border=1, align='R')
        pdf.cell(50, 8, f"R$ {s['icms']:,.2f}", border=1, align='R')
        pdf.ln()
    
    # Detalhamento por CFOP (páginas separadas)
    for cfop in sorted(dados_por_cfop.keys()):
        records = dados_por_cfop[cfop]
        pdf.add_page(orientation='L')
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, f"CFOP {cfop} - {len(records)} registros", ln=True, align='C')
        pdf.ln(5)
        _draw_pdf_table(pdf, records)
    
    # Salvar
    pdf_path = os.path.join(output_dir, filename)
    pdf.output(pdf_path)
    logger.info(f"PDF consolidado gerado: {pdf_path}")
    
    return len(all_records)


def _draw_pdf_table(pdf: FPDF, records: List[SpedRecord]) -> None:
    """
    Desenha tabela de registros no PDF, agrupando quando nota e alíquota são iguais.
    
    Args:
        pdf: Objeto FPDF
        records: Lista de SpedRecord para desenhar
    """
    pdf.set_font("Arial", 'B', 10)
    header = ["CFOP", "Nota Fiscal", "Valor Oper.", "Base ICMS", "Aliquota", "Valor ICMS"]
    col_widths = [25, 35, 45, 45, 30, 45]
    
    for i, h in enumerate(header):
        pdf.cell(col_widths[i], 10, h, border=1, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    totals: dict = defaultdict(float)
    
    # Agrupar registros por (numero_doc, aliquota)
    from collections import OrderedDict
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
    
    # Desenhar linhas agrupadas
    for key, data in grouped.items():
        pdf.cell(col_widths[0], 8, data['cfop'], border=1)
        pdf.cell(col_widths[1], 8, data['numero_doc'], border=1)
        pdf.cell(col_widths[2], 8, f"R$ {data['valor_operacao']:,.2f}", border=1, align='R')
        pdf.cell(col_widths[3], 8, f"R$ {data['base_icms']:,.2f}", border=1, align='R')
        pdf.cell(col_widths[4], 8, f"{data['aliquota']:.2f}%", border=1, align='R')
        pdf.cell(col_widths[5], 8, f"R$ {data['valor_icms']:,.2f}", border=1, align='R')
        pdf.ln()
        totals['valor_operacao'] += data['valor_operacao']
        totals['base_icms'] += data['base_icms']
        totals['valor_icms'] += data['valor_icms']
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(col_widths[0] + col_widths[1], 10, "TOTAIS", border=1, align='C')
    pdf.cell(col_widths[2], 10, f"R$ {totals['valor_operacao']:,.2f}", border=1, align='R')
    pdf.cell(col_widths[3], 10, f"R$ {totals['base_icms']:,.2f}", border=1, align='R')
    pdf.cell(col_widths[4], 10, "", border=1)
    pdf.cell(col_widths[5], 10, f"R$ {totals['valor_icms']:,.2f}", border=1, align='R')
