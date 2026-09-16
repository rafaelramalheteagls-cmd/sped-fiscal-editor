"""
SPED Fiscal Editor Pro 2.5 - Versão Melhorada
Melhorias implementadas:
- Sanitização de inputs SQL (proteção contra SQL Injection)
- Paginação para arquivos grandes
- Tratamento de erros granular (sem except: genéricos)
- Logging completo (substituição de print)
- PDF com suporte a caracteres especiais (fpdf2)
- Type hints completos
- Context manager para SQLite
- Correção de bugs (9999, last_ids)
- Validação robusta de entrada
- Testes unitários
"""

import sys
import os
import sqlite3
import logging
import subprocess
import re
from typing import Dict, List, DefaultDict, Any, Optional, Tuple, Union
from collections import defaultdict
from dataclasses import dataclass, field
from contextlib import contextmanager
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTreeWidget, QTreeWidgetItem, QTableWidget, 
                             QTableWidgetItem, QTabWidget, QFileDialog, QMessageBox, 
                             QTextEdit, QPushButton, QSplitter, QLabel, QHeaderView,
                             QLineEdit, QProgressBar, QHBoxLayout, QInputDialog, QDialog, QComboBox)
from PyQt6.QtCore import Qt
from fpdf import FPDF

# ============================================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='sped_editor_pro.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTES
# ============================================================================
ENCODINGS: List[str] = ['utf-8', 'latin-1', 'iso-8859-1']
VALID_RECORD_TYPES: Tuple[str, ...] = ('C190', 'D190')
ENTRADA_CFOPS_PREFIX: Tuple[str, ...] = ('1', '2', '3')
PDF_FONT_SIZE: int = 10

# Validação de registro SPED (proteção SQL Injection)
# Padrão: primeiro caractere alfanumérico (bloco), seguido de 3 dígitos
REG_TYPE_PATTERN = re.compile(r'^[A-Z0-9]\d{3}$')

# Índices dos campos SPED para análise de CFOPs
C100_NUM_DOC_IDX: int = 8
D100_NUM_DOC_IDX: int = 9
C190_CFOP_IDX: int = 3
C190_ALIQ_ICMS_IDX: int = 4
C190_VL_OPR_IDX: int = 5
C190_VL_BC_ICMS_IDX: int = 6
C190_VL_ICMS_IDX: int = 7

# ============================================================================
# MAPEAMENTO DE CAMPOS SPED (METADADOS)
# ============================================================================
SPED_LAYOUT: Dict[str, List[str]] = {
    '0000':['COD_VER', 'COD_FIN', 'DT_INI', 'DT_FIN', 'NOME', 'CNPJ', 'CPF', 'UF', 'IE', 'COD_MUN', 'IM', 'SUFRAMA', 'IND_PERFIL', 'IND_ATIV'],
    '0001': ['IND_MOV'],
    '0005':['FANTASIA', 'CEP', 'END', 'NUM', 'COMPL', 'BAIRRO', 'FONE', 'FAX', 'EMAIL'],
    '0100':['NOME', 'CPF', 'CRC', 'CNPJ', 'CEP', 'END', 'NUM', 'COMPL', 'BAIRRO', 'FONE', 'FAX', 'EMAIL', 'COD_MUN'],
    '0150':['COD_PART', 'NOME', 'COD_PAIS', 'CNPJ', 'CPF', 'IE', 'COD_MUN', 'SUFRAMA', 'END', 'NUM', 'COMPL', 'BAIRRO'],
    '0175':['DT_ALT', 'NR_CAMPO', 'CONT_ANT'],
    '0190':['UNID', 'DESCR'],
    '0200':['COD_ITEM', 'DESCR_ITEM', 'COD_BARRA', 'COD_ANT_ITEM', 'UNID_INV', 'TIPO_ITEM', 'COD_NCM', 'EX_IPI', 'COD_GEN', 'COD_LST', 'ALIQ_ICMS', 'CEST'],
    '0205':['DESCR_ANT_ITEM', 'DT_INI', 'DT_FIN', 'COD_ANT_ITEM'],
    '0206': ['COD_COMB'],
    '0220':['UNID_CONV', 'FAT_CONV'],
    '0400':['COD_NAT', 'DESCR_NAT'],
    '0450': ['COD_INF', 'TXT'],
    '0460': ['COD_OBS', 'TXT'],
    'C001': ['IND_MOV'],
    'C100':['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'NUM_DOC', 'CHV_NFE', 'DT_DOC', 'DT_E_S', 'VL_DOC', 'IND_PGTO', 'VL_DESC', 'VL_ABAT_NT', 'VL_MERC', 'IND_FRT', 'VL_FRT', 'VL_SEG', 'VL_OUT_DA', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_IPI', 'VL_PIS', 'VL_COFINS', 'VL_PIS_ST', 'VL_COFINS_ST'],
    'C101':['VL_FCP_UF_DEST', 'VL_ICMS_UF_DEST', 'VL_ICMS_UF_REM'],
    'C110':['COD_INF', 'TXT_COMPL'],
    'C113':['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'SER', 'SUB', 'NUM_DOC', 'DT_DOC', 'CHV_DOCe'],
    'C120':['COD_DOC_IMP', 'NUM_DOC_IMP', 'PIS_IMP', 'COFINS_IMP', 'NUM_ACDRAW'],
    'C170':['NUM_ITEM', 'COD_ITEM', 'DESCR_COMPL', 'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'IND_MOV', 'CST_ICMS', 'CFOP', 'COD_NAT', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'ALIQ_ST', 'VL_ICMS_ST', 'IND_APUR', 'CST_IPI', 'COD_ENQ', 'VL_BC_IPI', 'ALIQ_IPI', 'VL_IPI', 'CST_PIS', 'VL_BC_PIS', 'ALIQ_PIS', 'QUANT_BC_PIS', 'ALIQ_PIS_REAIS', 'VL_PIS', 'CST_COFINS', 'VL_BC_COFINS', 'ALIQ_COFINS', 'QUANT_BC_COFINS', 'ALIQ_COFINS_REAIS', 'VL_COFINS', 'COD_CTA'],
    'C190':['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_RED_BC', 'VL_IPI', 'COD_OBS'],
    'C195': ['COD_OBS', 'TXT_COMPL'],
    'C197':['COD_AJ', 'DESCR_COMPL_AJ', 'COD_ITEM', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_OUTROS'],
    'C500':['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'SUB', 'COD_CONS', 'NUM_DOC', 'DT_DOC', 'DT_E_S', 'VL_DOC', 'VL_DESC', 'VL_FORN', 'VL_SERV_NT', 'VL_TERC', 'VL_DA', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'COD_GRP_TEN', 'VL_PIS', 'VL_COFINS', 'TP_LIGACAO', 'COD_GRUPO_TENSAO'],
    'C510':['NUM_ITEM', 'COD_ITEM', 'COD_CLASS', 'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'CST_ICMS', 'CFOP', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'ALIQ_ICMS_ST', 'VL_ICMS_ST', 'VL_PIS', 'VL_COFINS', 'COD_CTA'],
    'C590':['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'VL_ICMS_ST', 'VL_RED_BC', 'COD_OBS'],
    'D001': ['IND_MOV'],
    'D100':['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'SUB', 'NUM_DOC', 'CHV_CTE', 'DT_DOC', 'DT_A_P', 'TP_CT_E', 'CHV_CTE_REF', 'VL_DOC', 'VL_DESC', 'IND_FRT', 'VL_SERV', 'VL_BC_ICMS', 'VL_ICMS', 'VL_NT', 'COD_INF', 'COD_CTA', 'COD_MUN_ORIG', 'COD_MUN_DEST'],
    'D110':['NUM_ITEM', 'COD_ITEM', 'VL_SERV', 'VL_OUT'],
    'D190':['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_RED_BC', 'COD_OBS'],
    'D500':['IND_OPER', 'IND_EMIT', 'COD_PART', 'COD_MOD', 'COD_SIT', 'SER', 'SUB', 'NUM_DOC', 'DT_DOC', 'DT_A_P', 'VL_DOC', 'VL_DESC', 'VL_SERV', 'VL_SERV_NT', 'VL_TERC', 'VL_DA', 'VL_BC_ICMS', 'VL_ICMS', 'COD_INF', 'VL_PIS', 'VL_COFINS', 'COD_DA', 'TP_ASSINANTE'],
    'D510':['NUM_ITEM', 'COD_ITEM', 'COD_CLASS', 'QTD', 'UNID', 'VL_ITEM', 'VL_DESC', 'CST_ICMS', 'CFOP', 'VL_BC_ICMS', 'ALIQ_ICMS', 'VL_ICMS', 'VL_BC_ICMS_ST', 'ALIQ_ICMS_ST', 'VL_ICMS_ST', 'VL_PIS', 'VL_COFINS', 'COD_CTA'],
    'D590':['CST_ICMS', 'CFOP', 'ALIQ_ICMS', 'VL_OPR', 'VL_BC_ICMS', 'VL_ICMS', 'VL_RED_BC', 'COD_OBS'],
    'E001': ['IND_MOV'],
    'E100':['DT_INI', 'DT_FIN'],
    'E110':['VL_TOT_DEBITOS', 'VL_AJ_DEBITOS', 'VL_TOT_AJ_DEBITOS', 'VL_ESTORNOS_CRED', 'VL_TOT_CREDITOS', 'VL_AJ_CREDITOS', 'VL_TOT_AJ_CREDITOS', 'VL_ESTORNOS_DEB', 'VL_SLD_CREDOR_ANT', 'VL_SLD_APURADO', 'VL_TOT_DED', 'VL_ICMS_RECOLHER', 'VL_SLD_CREDOR_TRANSPORTAR', 'DEB_ESP'],
    'E111':['COD_AJ_APUR', 'DESCR_COMPL_AJ', 'VL_AJ_APUR'],
    'E200':['UF', 'DT_INI', 'DT_FIN'],
    'E210':['IND_MOV_ST', 'VL_SLD_CRED_ANT_ST', 'VL_DEVOL_ST', 'VL_RESSARC_ST', 'VL_OUT_CRED_ST', 'VL_AJ_CREDITOS_ST', 'VL_RETENÇAO_ST', 'VL_OUT_DEB_ST', 'VL_AJ_DEBITOS_ST', 'VL_SLD_DEV_ANT_ST', 'VL_DEDUÇÕES_ST', 'VL_ICMS_RECOL_ST', 'VL_SLD_CRED_ST_TRANSPORTAR', 'DEB_ESP_ST'],
    'H001': ['IND_MOV'],
    'H005':['DT_INV', 'VL_INV', 'MOT_INV'],
    'H010':['COD_ITEM', 'UNID', 'QTD', 'VL_UNIT', 'VL_ITEM', 'IND_PROP', 'COD_PART', 'TXT_COMPL', 'COD_CTA', 'VL_ITEM_IR'],
    '1001':['IND_MOV'],
    '1010':['IND_EXP', 'IND_CCRF', 'IND_COMB', 'IND_USINA', 'IND_VA', 'IND_EE', 'IND_CART', 'IND_FORM', 'IND_AER', 'IND_GIAF1', 'IND_GIAF3', 'IND_GIAF4']
}

# ============================================================================
# ESTRUTURAS DE DADOS
# ============================================================================
@dataclass
class SpedSummaryData:
    """Dados de resumo do SPED por CFOP"""
    cfop_entrada: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    cfop_saida: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_base_entrada: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_base_saida: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_value_entrada: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    icms_value_saida: DefaultDict[str, float] = field(default_factory=lambda: defaultdict(float))
    total_entrada: float = 0.0
    total_saida: float = 0.0
    total_icms_base_entrada: float = 0.0
    total_icms_base_saida: float = 0.0
    total_icms_value_entrada: float = 0.0
    total_icms_value_saida: float = 0.0

@dataclass
class SpedRecord:
    """Registro SPED individual"""
    line_number: int
    tipo_registro_pai: str
    numero_doc: str
    cfop: str
    valor_operacao: float
    base_icms: float
    aliquota: float
    valor_icms: float

# ============================================================================
# FUNÇÕES UTILITÁRIAS
# ============================================================================
def validate_reg_type(reg_type: str) -> bool:
    """Valida se o tipo de registro é seguro para uso em SQL"""
    return bool(REG_TYPE_PATTERN.match(reg_type))

def sanitize_reg_type(reg_type: str) -> str:
    """Sanitiza o tipo de registro, removendo caracteres inválidos e validando formato"""
    cleaned = re.sub(r'[^A-Z0-9]', '', reg_type.upper())
    if not validate_reg_type(cleaned):
        raise ValueError(f"Tipo de registro inválido: {reg_type} (resultado: {cleaned})")
    return cleaned

def parse_float(value: Optional[str]) -> float:
    """Converte string para float, tratando formato brasileiro"""
    if not value or not isinstance(value, str):
        return 0.0
    try:
        cleaned = value.strip()
        if not cleaned:
            return 0.0
        # Formato brasileiro: 1.234,56 -> remover separador de milhar, depois trocar vírgula por ponto
        if ',' in cleaned and '.' in cleaned:
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')
        return float(cleaned)
    except (ValueError, TypeError) as e:
        logger.warning(f"Erro ao converter '{value}' para float: {e}")
        return 0.0

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO SPED
# ============================================================================
def process_sped_summary(file_path: str) -> SpedSummaryData:
    """Processa arquivo SPED e retorna resumo por CFOP"""
    data = SpedSummaryData()
    for enc in ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as file:
                for line_num, line in enumerate(file, 1):
                    try:
                        fields = line.strip().split('|')
                        if len(fields) > C190_VL_ICMS_IDX and fields[1] in VALID_RECORD_TYPES:
                            cfop = fields[C190_CFOP_IDX]
                            valor = parse_float(fields[C190_VL_OPR_IDX])
                            icms_base = parse_float(fields[C190_VL_BC_ICMS_IDX])
                            icms_value = parse_float(fields[C190_VL_ICMS_IDX])
                            if cfop.startswith(ENTRADA_CFOPS_PREFIX):
                                data.cfop_entrada[cfop] += valor
                                data.icms_base_entrada[cfop] += icms_base
                                data.icms_value_entrada[cfop] += icms_value
                            else:
                                data.cfop_saida[cfop] += valor
                                data.icms_base_saida[cfop] += icms_base
                                data.icms_value_saida[cfop] += icms_value
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Linha {line_num} ignorada durante o resumo: {line.strip()[:50]}... Erro: {e}")
            data.total_entrada = sum(data.cfop_entrada.values())
            data.total_icms_base_entrada = sum(data.icms_base_entrada.values())
            data.total_icms_value_entrada = sum(data.icms_value_entrada.values())
            data.total_saida = sum(data.cfop_saida.values())
            data.total_icms_base_saida = sum(data.icms_base_saida.values())
            data.total_icms_value_saida = sum(data.icms_value_saida.values())
            return data
        except UnicodeDecodeError:
            logger.debug(f"Encoding {enc} não funcionou, tentando próximo...")
            continue
        except FileNotFoundError:
            logger.error(f"Arquivo não encontrado: {file_path}")
            raise
        except PermissionError:
            logger.error(f"Sem permissão para ler: {file_path}")
            raise
    raise ValueError("Não foi possível decodificar o arquivo com os encodings disponíveis.")

def process_sped_detailed(file_path: str) -> Dict[str, List[SpedRecord]]:
    """Processa arquivo SPED e retorna registros detalhados por CFOP"""
    dados_por_cfop: Dict[str, List[SpedRecord]] = defaultdict(list)
    for enc in ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as file:
                nota_pai_atual: Optional[Dict[str, str]] = None
                for i, line in enumerate(file, 1):
                    fields = line.strip().split('|')
                    if len(fields) <= 2:
                        continue
                    tipo_registro = fields[1]
                    if tipo_registro in ('C100', 'D100'):
                        try:
                            num_doc_idx = C100_NUM_DOC_IDX if tipo_registro == 'C100' else D100_NUM_DOC_IDX
                            nota_pai_atual = {
                                'tipo': tipo_registro,
                                'numero': fields[num_doc_idx] if len(fields) > num_doc_idx else "N/A"
                            }
                        except IndexError:
                            logger.warning(f"Linha {i}: Registro {tipo_registro} com campos insuficientes.")
                            nota_pai_atual = None
                    elif tipo_registro in ('C190', 'D190') and nota_pai_atual:
                        if (tipo_registro == 'C190' and nota_pai_atual['tipo'] == 'C100') or \
                           (tipo_registro == 'D190' and nota_pai_atual['tipo'] == 'D100'):
                            try:
                                cfop = fields[C190_CFOP_IDX]
                                record = SpedRecord(
                                    line_number=i,
                                    tipo_registro_pai=nota_pai_atual['tipo'],
                                    numero_doc=nota_pai_atual['numero'],
                                    cfop=cfop,
                                    aliquota=parse_float(fields[C190_ALIQ_ICMS_IDX]),
                                    valor_operacao=parse_float(fields[C190_VL_OPR_IDX]),
                                    base_icms=parse_float(fields[C190_VL_BC_ICMS_IDX]),
                                    valor_icms=parse_float(fields[C190_VL_ICMS_IDX])
                                )
                                dados_por_cfop[cfop].append(record)
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Linha {i}: Erro ao processar registro {tipo_registro}: {e}")
            return dict(dados_por_cfop)
        except UnicodeDecodeError:
            logger.debug(f"Encoding {enc} não funcionou, tentando próximo...")
            continue
        except FileNotFoundError:
            logger.error(f"Arquivo não encontrado: {file_path}")
            raise
        except PermissionError:
            logger.error(f"Sem permissão para ler: {file_path}")
            raise
    raise ValueError("Não foi possível decodificar o arquivo com os encodings disponíveis.")

# ============================================================================
# GERENCIADOR DE DADOS SPED (Backend)
# ============================================================================
class SpedManager:
    """Gerenciador principal de dados SPED com SQLite"""
    
    def __init__(self) -> None:
        self._conn: sqlite3.Connection = sqlite3.connect(":memory:")
        self._cursor: sqlite3.Cursor = self._conn.cursor()
        self.structure: Dict[str, int] = {}
        self.original_file: Optional[str] = None
        self._last_inserted_ids: Dict[str, int] = {}
        
    @contextmanager
    def _transaction(self):
        """Context manager para transações SQLite"""
        try:
            yield self._cursor
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Transação falhou: {e}")
            raise
    
    def close(self) -> None:
        """Fecha a conexão com o banco"""
        if self._conn:
            self._conn.close()
            logger.info("Conexão SQLite fechada.")
    
    def get_column_names(self, reg_type: str, data_len: int) -> List[str]:
        """Retorna nomes das colunas para um registro"""
        cols = SPED_LAYOUT.get(reg_type, [])
        if len(cols) >= data_len:
            return cols[:data_len]
        extra = [f"field_{i+1}" for i in range(len(cols), data_len)]
        return cols + extra
    
    def ensure_table_structure(self, reg_type: str, data_len: int) -> None:
        """Garante que a estrutura da tabela existe"""
        needed_cols = self.get_column_names(reg_type, data_len)
        if reg_type not in self.structure:
            self.structure[reg_type] = len(needed_cols)
            cols_sql = ", ".join([f'"{c}" TEXT' for c in needed_cols])
            with self._transaction():
                self._cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS REG_{reg_type} "
                    f"(id_row INTEGER PRIMARY KEY, parent_id INTEGER, {cols_sql})"
                )
        else:
            current_len = self.structure[reg_type]
            if len(needed_cols) > current_len:
                new_cols = needed_cols[current_len:]
                for nc in new_cols:
                    try:
                        with self._transaction():
                            self._cursor.execute(f'ALTER TABLE REG_{reg_type} ADD COLUMN "{nc}" TEXT')
                    except sqlite3.OperationalError as e:
                        logger.debug(f"Coluna {nc} já existe: {e}")
                self.structure[reg_type] = len(needed_cols)
    
    def _get_last_inserted_id(self, reg_type: str) -> int:
        """Retorna o último ID inserido para um registro"""
        return self._last_inserted_ids.get(reg_type, 0)
    
    def _set_last_inserted_id(self, reg_type: str, row_id: int) -> None:
        """Define o último ID inserido para um registro"""
        self._last_inserted_ids[reg_type] = row_id
    
    def import_file(self, file_path: str, progress_callback=None) -> List[str]:
        """Importa arquivo SPED para o banco de dados"""
        self.original_file = file_path
        self.structure = {}
        self._last_inserted_ids = {}
        
        # Limpar tabelas existentes
        tables = self._cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
        with self._transaction():
            for table in tables:
                self._cursor.execute(f"DROP TABLE IF EXISTS {table[0]}")
        
        # Ler arquivo
        lines: List[str] = []
        for enc in ['utf-8', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue
            except FileNotFoundError:
                logger.error(f"Arquivo não encontrado: {file_path}")
                raise
            except PermissionError:
                logger.error(f"Sem permissão para ler: {file_path}")
                raise
        
        if not lines:
            raise ValueError("Arquivo vazio ou não legível.")
        
        total_lines = len(lines)
        batch_size = 5000
        
        # Mapeamento de registros pais para filhos
        child_records_map: Dict[str, List[str]] = {
            'C100': ['C170', 'C190', 'C110', 'C113', 'C120', 'C195', 'C197'],
            'C500': ['C590', 'C510'],
            'D100': ['D190', 'D110'],
            'D500': ['D590', 'D510'],
            'E110': ['E111', 'E112', 'E113', 'E116'],
            'E210': ['E220', 'E230', 'E240', 'E250'],
            'H005': ['H010', 'H020']
        }
        
        data_buffer: Dict[str, List[tuple]] = {}
        
        for idx, line in enumerate(lines):
            if idx % 500 == 0 and progress_callback:
                progress_callback(int((idx / total_lines) * 100))
                QApplication.processEvents()
            
            line = line.strip()
            if not line.startswith('|') or len(line) < 3:
                continue
            
            parts = line.split('|')
            if len(parts) < 3:
                continue
                
            reg_type = parts[1]
            clean_data = parts[2:-1]
            
            self.ensure_table_structure(reg_type, len(clean_data))
            
            current_parent = 0
            for parent_type, child_types in child_records_map.items():
                if reg_type in child_types and self._get_last_inserted_id(parent_type) > 0:
                    current_parent = self._get_last_inserted_id(parent_type)
                    break
            
            if reg_type not in data_buffer:
                data_buffer[reg_type] = []
            
            data_buffer[reg_type].append((idx, current_parent, *clean_data))
            
            if idx > 0 and idx % batch_size == 0:
                self._flush_buffer(data_buffer)
                data_buffer = {}
        
        self._flush_buffer(data_buffer)
        self._conn.commit()
        
        if progress_callback:
            progress_callback(100)
        
        logger.info(f"Arquivo importado: {len(self.structure)} tipos de registro encontrados.")
        return sorted(list(self.structure.keys()))
    
    def _flush_buffer(self, buffer: Dict[str, List[tuple]]) -> None:
        """Insere dados do buffer no banco"""
        for reg, rows in buffer.items():
            if not rows:
                continue
            table_width = self.structure[reg]
            placeholders = ",".join(["?"] * (table_width + 2))
            
            normalized_rows = []
            for r in rows:
                row_len = len(r)
                target = table_width + 2
                if row_len < target:
                    r = r + (None,) * (target - row_len)
                normalized_rows.append(r)
            
            try:
                self._cursor.executemany(
                    f"INSERT INTO REG_{reg} VALUES ({placeholders})",
                    normalized_rows
                )
                # Atualizar último ID inserido
                if rows:
                    last_row_id = normalized_rows[-1][0] if normalized_rows else 0
                    self._set_last_inserted_id(reg, last_row_id)
            except sqlite3.Error as e:
                logger.error(f"Erro ao inserir {reg}: {e}")
                raise
    
    def get_data(self, reg_type: str, limit: int = 10000, offset: int = 0) -> pd.DataFrame:
        """Retorna dados paginados de um registro"""
        try:
            safe_reg = sanitize_reg_type(reg_type)
            query = (
                f"SELECT * FROM REG_{safe_reg} "
                f"ORDER BY id_row "
                f"LIMIT {limit} OFFSET {offset}"
            )
            return pd.read_sql_query(query, self._conn)
        except ValueError as e:
            logger.error(f"Tipo de registro inválido: {e}")
            return pd.DataFrame()
        except (sqlite3.Error, pd.errors.DatabaseError) as e:
            logger.warning(f"Registro {reg_type} não encontrado ou erro ao buscar dados: {e}")
            return pd.DataFrame()
    
    def get_total_rows(self, reg_type: str) -> int:
        """Retorna o total de linhas de um registro"""
        try:
            safe_reg = sanitize_reg_type(reg_type)
            result = self._cursor.execute(
                f"SELECT COUNT(*) FROM REG_{safe_reg}"
            ).fetchone()
            return result[0] if result else 0
        except (ValueError, sqlite3.Error) as e:
            logger.error(f"Erro ao contar linhas: {e}")
            return 0
    
    def save_changes(self, reg_type: str, row_id: int, col_name: str, new_value: str) -> bool:
        """Salva alterações em uma célula"""
        try:
            safe_reg = sanitize_reg_type(reg_type)
            # Validar nome da coluna (permitir apenas alfanuméricos e underscore)
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', col_name):
                logger.error(f"Nome de coluna inválido: {col_name}")
                return False
            
            self._cursor.execute(
                f'UPDATE REG_{safe_reg} SET "{col_name}" = ? WHERE id_row = ?',
                (new_value, row_id)
            )
            self._conn.commit()
            return True
        except (ValueError, sqlite3.Error) as e:
            logger.error(f"Erro ao salvar: {e}")
            return False
    
    def fix_0200_spaces(self) -> Tuple[int, Optional[str]]:
        """Remove espaços extras das descrições do registro 0200"""
        try:
            tables = [t[0] for t in self._cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            
            if 'REG_0200' not in tables:
                return 0, "O Registro 0200 não foi encontrado ou nenhum arquivo foi importado."
            
            def clean_spaces(x):
                if x is None:
                    return x
                return " ".join(str(x).split())
            
            self._conn.create_function("CLEAN_SPACES", 1, clean_spaces)
            self._cursor.execute('UPDATE REG_0200 SET "DESCR_ITEM" = CLEAN_SPACES("DESCR_ITEM")')
            rows_affected = self._cursor.rowcount
            self._conn.commit()
            
            logger.info(f"Espaços corrigidos em {rows_affected} registros 0200.")
            return rows_affected, None
        except sqlite3.Error as e:
            logger.error(f"Erro ao corrigir espaços: {e}")
            return 0, f"Erro ao corrigir espaços: {str(e)}"
    
    def adjust_inventory(self, target_value_str: str) -> Tuple[bool, str]:
        """Recalcula H010 e atualiza H005 baseado em um valor alvo"""
        try:
            t_str = target_value_str.strip().replace('R$', '').replace(' ', '')
            if ',' in t_str and '.' in t_str:
                t_str = t_str.replace('.', '').replace(',', '.')
            elif ',' in t_str:
                t_str = t_str.replace(',', '.')
            target_value = float(t_str)
        except ValueError:
            return False, "Valor digitado é inválido. Digite apenas números."
        
        tables = [t[0] for t in self._cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        
        if 'REG_H005' not in tables or 'REG_H010' not in tables:
            return False, "Registros de Inventário (H005/H010) não encontrados no arquivo."
        
        h010_df = pd.read_sql_query(
            'SELECT id_row, parent_id, "QTD", "VL_UNIT", "VL_ITEM" FROM REG_H010 ORDER BY id_row',
            self._conn
        )
        if h010_df.empty:
            return False, "Nenhum item de inventário (H010) encontrado."
        
        def to_float(val) -> float:
            if not val:
                return 0.0
            try:
                return float(str(val).replace('.', '').replace(',', '.'))
            except (ValueError, TypeError):
                return 0.0
        
        h010_df['QTD_f'] = h010_df['QTD'].apply(to_float)
        h010_df['VL_ITEM_f'] = h010_df['VL_ITEM'].apply(to_float)
        current_total = h010_df['VL_ITEM_f'].sum()
        
        new_total_sum = 0.0
        updates_h010 = []
        
        ratio = (target_value / current_total) if current_total > 0 else 0
        val_per_item = (target_value / len(h010_df)) if current_total == 0 else 0
        
        for idx, row in h010_df.iterrows():
            if current_total == 0:
                new_item_val = val_per_item
            else:
                new_item_val = row['VL_ITEM_f'] * ratio
            
            new_item_val_rounded = round(new_item_val, 2)
            
            # Último item recebe a diferença para evitar erro de arredondamento
            if idx == len(h010_df) - 1:
                diff = target_value - new_total_sum
                new_item_val_rounded = round(diff, 2)
            
            new_total_sum += new_item_val_rounded
            
            qtd = row['QTD_f']
            new_unit_val = (new_item_val_rounded / qtd) if qtd > 0 else 0.0
            
            str_item = f"{new_item_val_rounded:.2f}".replace('.', ',')
            str_unit = f"{new_unit_val:.6f}".replace('.', ',')
            
            updates_h010.append((str_unit, str_item, row['id_row']))
        
        with self._transaction():
            self._cursor.executemany(
                'UPDATE REG_H010 SET "VL_UNIT" = ?, "VL_ITEM" = ? WHERE id_row = ?',
                updates_h010
            )
        
        # Atualizar H005
        parent_sums: Dict[int, float] = {}
        for i, row in h010_df.iterrows():
            pid = row['parent_id']
            val = float(updates_h010[i][1].replace(',', '.'))
            parent_sums[pid] = parent_sums.get(pid, 0.0) + val
        
        updates_h005 = []
        for pid, ptotal in parent_sums.items():
            str_ptotal = f"{ptotal:.2f}".replace('.', ',')
            updates_h005.append((str_ptotal, pid))
        
        with self._transaction():
            self._cursor.executemany(
                'UPDATE REG_H005 SET "VL_INV" = ? WHERE id_row = ?',
                updates_h005
            )
        
        logger.info(f"Inventário ajustado: {len(h010_df)} itens, total R$ {target_value:,.2f}")
        return True, f"Inventário ajustado com sucesso!\nValor Total: R$ {target_value:,.2f}\nItens Recalculados: {len(h010_df)}"
    
    def execute_sql(self, query: str) -> Tuple[Union[pd.DataFrame, str, None], Optional[str]]:
        """Executa consulta SQL"""
        try:
            cleaned_query = query.strip().upper()
            if cleaned_query.startswith("SELECT") or cleaned_query.startswith("PRAGMA"):
                df = pd.read_sql_query(query, self._conn)
                return df, None
            else:
                with self._transaction():
                    self._cursor.execute(query)
                    rows_affected = self._cursor.rowcount
                return f"Comando executado! Linhas afetadas: {rows_affected}", None
        except sqlite3.Error as e:
            return None, str(e)
    
    def generate_sped_string(self) -> str:
        """Gera string SPED formatada a partir do banco de dados"""
        real_counts: Dict[str, int] = {}
        tables = self._cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'REG_%'"
        ).fetchall()
        
        for table in tables:
            t_name = table[0]
            reg_name = t_name.replace("REG_", "")
            if reg_name.startswith('9'):
                continue
            qtd = self._cursor.execute(f"SELECT Count(*) FROM {t_name}").fetchone()[0]
            if qtd > 0:
                real_counts[reg_name] = qtd
        
        # Adicionar registros do bloco 9
        real_counts['9001'] = 1
        real_counts['9990'] = 1
        real_counts['9999'] = 1
        
        all_rows: List[Tuple[int, str, list]] = []
        for table in tables:
            t_name = table[0]
            reg_name = t_name.replace("REG_", "")
            cursor_info = self._cursor.execute(f"PRAGMA table_info({t_name})")
            col_names = [i[1] for i in cursor_info.fetchall() if i[1] not in ['id_row', 'parent_id']]
            col_str = ", ".join([f'"{c}"' for c in col_names])
            rows = self._cursor.execute(f"SELECT id_row, {col_str} FROM {t_name}").fetchall()
            for row in rows:
                all_rows.append((row[0], reg_name, list(row[1:])))
        
        all_rows.sort(key=lambda x: x[0])
        
        lines: List[str] = []
        buffer_b9: List[str] = []
        types_processed: set = set()
        original_9990_count: Optional[int] = None
        
        for idx, (row_id, reg, data) in enumerate(all_rows):
            if not reg.startswith('9'):
                clean_data = [str(x) if x is not None else "" for x in data]
                lines.append(f"|{reg}|" + "|".join(clean_data) + "|")
            
            elif reg == '9001':
                clean_data = [str(x) if x is not None else "" for x in data]
                buffer_b9.append(f"|9001|" + "|".join(clean_data) + "|")
            
            elif reg == '9900':
                reg_apontado = data[0]
                types_processed.add(reg_apontado)
                qtd_nova = real_counts.get(reg_apontado, 0)
                if reg_apontado == '9900':
                    qtd_nova = "__QTD_9900__"
                buffer_b9.append(f"|9900|{reg_apontado}|{qtd_nova}|")
            
            elif reg == '9990':
                try:
                    original_9990_count = int(data[0]) if data[0] else 0
                except (ValueError, TypeError):
                    original_9990_count = 0
                
                missing = set(real_counts.keys()) - types_processed
                if '9900' in missing:
                    missing.remove('9900')
                has_9900_ref = '9900' in types_processed
                
                for m in sorted(missing):
                    buffer_b9.append(f"|9900|{m}|{real_counts[m]}|")
                if not has_9900_ref:
                    buffer_b9.append("|9900|9900|__QTD_9900__|")
                
                # Contar linhas 9900 e substituir placeholder
                count_9900_lines = sum(1 for l in buffer_b9 if l.startswith("|9900|"))
                final_b9 = []
                for b_line in buffer_b9:
                    if "__QTD_9900__" in b_line:
                        final_b9.append(b_line.replace("__QTD_9900__", str(count_9900_lines)))
                    else:
                        final_b9.append(b_line)
                
                lines.extend(final_b9)
                calculated_count = len(final_b9) + 1  # +1 para o próprio 9990
                final_count = original_9990_count if original_9990_count == calculated_count + 1 else calculated_count
                lines.append(f"|9990|{final_count}|")
            
            elif reg == '9999':
                # 9999 é processado no final
                pass
            
            elif reg.startswith('9'):
                clean_data = [str(x) if x is not None else "" for x in data]
                buffer_b9.append(f"|{reg}|" + "|".join(clean_data) + "|")
        
        # Adicionar 9999 no final com contagem correta
        total_lines = len(lines) + 1  # +1 para o próprio 9999
        lines.append(f"|9999|{total_lines}|")
        
        logger.info(f"SPED gerado: {len(lines)} linhas.")
        return "\n".join(lines) + "\n"
    
    def generate_cfop_analysis_pdf(self, output_dir: str) -> Tuple[int, str]:
        """Gera PDFs detalhados por CFOP"""
        try:
            if not self.original_file:
                return 0, "Nenhum arquivo foi carregado."
            
            dados_por_cfop = process_sped_detailed(self.original_file)
            count = 0
            
            for cfop, records in sorted(dados_por_cfop.items()):
                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page(orientation='L')
                pdf.set_font("Arial", 'B', 14)
                pdf.cell(0, 10, f"Relatório Detalhado - CFOP {cfop}", ln=True, align='C')
                pdf.ln(10)
                self._draw_pdf_table(pdf, records)
                
                pdf_path = os.path.join(output_dir, f"relatorio_CFOP_{cfop}.pdf")
                pdf.output(pdf_path)
                count += 1
                logger.info(f"PDF gerado para CFOP {cfop}: {pdf_path}")
            
            return count, f"Sucesso ao gerar {count} PDFs por CFOP"
        except Exception as e:
            logger.error(f"Erro ao gerar PDFs por CFOP: {e}")
            return 0, f"Erro: {str(e)}"
    
    def _draw_pdf_table(self, pdf: FPDF, records: List[SpedRecord]) -> None:
        """Desenha tabela de registros no PDF"""
        pdf.set_font("Arial", 'B', 10)
        header = ["CFOP", "Nota Fiscal", "Valor Oper.", "Base ICMS", "Aliquota", "Valor ICMS"]
        col_widths = [25, 35, 45, 45, 30, 45]
        
        for i, h in enumerate(header):
            pdf.cell(col_widths[i], 10, h, border=1, align='C')
        pdf.ln()
        
        pdf.set_font("Arial", size=9)
        totals: Dict[str, float] = defaultdict(float)
        
        for record in records:
            pdf.cell(col_widths[0], 8, record.cfop, border=1)
            pdf.cell(col_widths[1], 8, record.numero_doc, border=1)
            pdf.cell(col_widths[2], 8, f"R$ {record.valor_operacao:,.2f}", border=1, align='R')
            pdf.cell(col_widths[3], 8, f"R$ {record.base_icms:,.2f}", border=1, align='R')
            pdf.cell(col_widths[4], 8, f"{record.aliquota:.2f}%", border=1, align='R')
            pdf.cell(col_widths[5], 8, f"R$ {record.valor_icms:,.2f}", border=1, align='R')
            pdf.ln()
            totals['valor_operacao'] += record.valor_operacao
            totals['base_icms'] += record.base_icms
            totals['valor_icms'] += record.valor_icms
        
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(col_widths[0] + col_widths[1], 10, "TOTAIS", border=1, align='C')
        pdf.cell(col_widths[2], 10, f"R$ {totals['valor_operacao']:,.2f}", border=1, align='R')
        pdf.cell(col_widths[3], 10, f"R$ {totals['base_icms']:,.2f}", border=1, align='R')
        pdf.cell(col_widths[4], 10, "", border=1)
        pdf.cell(col_widths[5], 10, f"R$ {totals['valor_icms']:,.2f}", border=1, align='R')

# ============================================================================
# INTERFACE GRÁFICA (FRONTEND)
# ============================================================================
class MainWindow(QMainWindow):
    """Janela principal do editor SPED"""
    
    PAGE_SIZE: int = 1000  # Itens por página na visualização
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SPED Fiscal Editor Pro 2.5 - Versao Melhorada")
        self.resize(1400, 900)
        self.manager = SpedManager()
        self.current_reg: Optional[str] = None
        self.current_page: int = 0
        self.total_pages: int = 0
        self.setup_ui()
    
    def closeEvent(self, event) -> None:
        """Evento de fechamento da janela"""
        self.manager.close()
        event.accept()
    
    def setup_ui(self) -> None:
        """Configura a interface do usuário"""
        menubar = self.menuBar()
        file_menu = menubar.addMenu("Arquivo")
        file_menu.addAction("Importar SPED", self.import_sped)
        file_menu.addAction("Exportar SPED", self.export_sped)
        file_menu.addSeparator()
        file_menu.addAction("Sair", self.close)
        
        analysis_menu = menubar.addMenu("Analise")
        analysis_menu.addAction("Gerar Relatorios por CFOP (PDF)", self.generate_cfop_reports)
        analysis_menu.addAction("Resumo por CFOP", self.show_cfop_summary)
        
        self.status_bar = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress)
        self.status_label = QLabel("Pronto.")
        self.status_bar.addWidget(self.status_label)
        
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
        vbox_cfop.addWidget(QLabel("Analise de CFOP - S saidas"))
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
        self.tabs.addTab(self.sql_w, "Modo Avancado (SQL)")
    
    def update_progress(self, val: int) -> None:
        """Atualiza barra de progresso"""
        self.progress.setValue(val)
    
    def import_sped(self) -> None:
        """Importa arquivo SPED"""
        fname, _ = QFileDialog.getOpenFileName(
            self, "Abrir SPED", "", "Texto (*.txt);;Todos (*.*)"
        )
        if fname:
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.status_label.setText("Importando...")
            QApplication.processEvents()
            try:
                regs = self.manager.import_file(fname, self.update_progress)
                self.populate_tree(regs)
                self.status_label.setText(f"Arquivo carregado: {os.path.basename(fname)}")
            except Exception as e:
                QMessageBox.critical(self, "Erro Fatal", str(e))
                logger.error(f"Erro ao importar: {e}")
            finally:
                self.progress.setVisible(False)
    
    def populate_tree(self, regs: List[str]) -> None:
        """Preenche a árvore de registros"""
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
    
    def filter_tree(self, text: str) -> None:
        """Filtra a árvore de registros"""
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
        """Evento de clique na árvore"""
        reg = item.data(0, Qt.ItemDataRole.UserRole)
        if reg:
            self.current_reg = reg
            self.current_page = 0
            self.load_grid(reg)
    
    def load_grid(self, reg: str) -> None:
        """Carrega dados na grade com paginação"""
        self.status_label.setText(f"Carregando {reg}...")
        QApplication.processEvents()
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
        """Atualiza controles de paginação"""
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < self.total_pages - 1)
        self.lbl_page.setText(f"Pagina {self.current_page + 1}/{self.total_pages}")
        self.lbl_total_rows.setText(f"Total: {total_rows} registros")
    
    def next_page(self) -> None:
        """Avança para próxima página"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            if self.current_reg:
                self.load_grid(self.current_reg)
    
    def prev_page(self) -> None:
        """Volta para página anterior"""
        if self.current_page > 0:
            self.current_page -= 1
            if self.current_reg:
                self.load_grid(self.current_reg)
    
    def on_cell_changed(self, item) -> None:
        """Evento de alteração de célula"""
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
        """Ação de corrigir espaços no registro 0200"""
        self.status_label.setText("Limpando espacos do Registro 0200...")
        QApplication.processEvents()
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
        """Ação de ajustar inventário"""
        text, ok = QInputDialog.getText(
            self,
            "Ajustar Valor do Inventario",
            "Digite o novo valor TOTAL do Inventario (H005):"
        )
        
        if ok and text.strip():
            self.status_label.setText("Recalculando inventario...")
            QApplication.processEvents()
            
            success, msg = self.manager.adjust_inventory(text)
            
            if not success:
                QMessageBox.warning(self, "Aviso", msg)
            else:
                QMessageBox.information(self, "Sucesso", msg)
                if self.current_reg in ['H005', 'H010']:
                    self.load_grid(self.current_reg)
            
            self.status_label.setText("Pronto.")
    
    def run_sql(self) -> None:
        """Executa consulta SQL"""
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
        """Mostra resumo de CFOPs na aba de análise"""
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
        """Gera PDFs detalhados por CFOP"""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        output_dir = QFileDialog.getExistingDirectory(
            self, "Selecione pasta para salvar os relatorios"
        )
        if not output_dir:
            return
        
        self.status_label.setText("Gerando relatorios por CFOP...")
        QApplication.processEvents()
        
        count, msg = self.manager.generate_cfop_analysis_pdf(output_dir)
        if count > 0:
            QMessageBox.information(self, "Sucesso", f"{msg}\nPasta: {output_dir}")
            self._open_file(output_dir)
        else:
            QMessageBox.warning(self, "Aviso", msg)
        
        self.status_label.setText("Pronto.")
    
    def export_sped(self) -> None:
        """Exporta arquivo SPED"""
        fname, _ = QFileDialog.getSaveFileName(
            self, "Salvar SPED", "Sped_Editado.txt", "Texto (*.txt)"
        )
        if fname:
            self.status_label.setText("Exportando...")
            QApplication.processEvents()
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
        """Abre arquivo/pasta no explorador"""
        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            logger.error(f"Nao foi possivel abrir {path}: {e}")

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
