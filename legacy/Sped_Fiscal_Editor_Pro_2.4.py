import sys
import os
import sqlite3
import logging
import subprocess
import re
from typing import Dict, List, DefaultDict, Any, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
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
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='sped_editor_pro.log',
    filemode='w'
)

# ============================================================================
# CONSTANTES
# ============================================================================
ENCODINGS = ['utf-8', 'latin-1', 'iso-8859-1']
VALID_RECORD_TYPES = ('C190', 'D190')
ENTRADA_CFOPS_PREFIX = ('1', '2', '3')
PDF_FONT_SIZE = 10

# Índices dos campos SPED para análise de CFOPs
C100_NUM_DOC_IDX = 8
D100_NUM_DOC_IDX = 9
C190_CFOP_IDX = 3
C190_ALIQ_ICMS_IDX = 4
C190_VL_OPR_IDX = 5
C190_VL_BC_ICMS_IDX = 6
C190_VL_ICMS_IDX = 7

# ============================================================================
# MAPEAMENTO DE CAMPOS SPED (METADADOS)
# ============================================================================
SPED_LAYOUT = {
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
    line_number: int
    tipo_registro_pai: str
    numero_doc: str
    cfop: str
    valor_operacao: float
    base_icms: float
    aliquota: float
    valor_icms: float

# ============================================================================
# FUNÇÕES DE PROCESSAMENTO SPED
# ============================================================================
def parse_float(value: str) -> float:
    if not value: return 0.0
    return float(value.replace(',', '.'))

def process_sped_summary(file_path: str) -> SpedSummaryData:
    """Processa arquivo SPED e retorna resumo por CFOP"""
    data = SpedSummaryData()
    for enc in ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as file:
                for line in file:
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
                        logging.warning(f"Linha ignorada durante o resumo: {line.strip()}. Erro: {e}")
            data.total_entrada = sum(data.cfop_entrada.values())
            data.total_icms_base_entrada = sum(data.icms_base_entrada.values())
            data.total_icms_value_entrada = sum(data.icms_value_entrada.values())
            data.total_saida = sum(data.cfop_saida.values())
            data.total_icms_base_saida = sum(data.icms_base_saida.values())
            data.total_icms_value_saida = sum(data.icms_value_saida.values())
            return data
        except UnicodeDecodeError: 
            continue
        except Exception as e:
            logging.error(f"Erro crítico ao processar {file_path} com encoding {enc}: {e}")
            raise
    raise ValueError("Não foi possível decodificar o arquivo com os encodings disponíveis.")

def process_sped_detailed(file_path: str) -> Dict[str, List[SpedRecord]]:
    """Processa arquivo SPED e retorna registros detalhados por CFOP"""
    dados_por_cfop = defaultdict(list)
    for enc in ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as file:
                nota_pai_atual = None
                for i, line in enumerate(file):
                    fields = line.strip().split('|')
                    if len(fields) <= 2: 
                        continue
                    tipo_registro = fields[1]
                    if tipo_registro in ('C100', 'D100'):
                        try:
                            num_doc_idx = C100_NUM_DOC_IDX if tipo_registro == 'C100' else D100_NUM_DOC_IDX
                            nota_pai_atual = {'tipo': tipo_registro, 'numero': fields[num_doc_idx] if len(fields) > num_doc_idx else "N/A"}
                        except IndexError:
                            logging.warning(f"Linha {i+1}: Registro {tipo_registro} com campos insuficientes.")
                            nota_pai_atual = None
                    elif tipo_registro in ('C190', 'D190') and nota_pai_atual:
                        if (tipo_registro == 'C190' and nota_pai_atual['tipo'] == 'C100') or (tipo_registro == 'D190' and nota_pai_atual['tipo'] == 'D100'):
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
                                logging.warning(f"Linha {i+1}: Erro ao processar registro {tipo_registro}: {e}")
            return dados_por_cfop
        except UnicodeDecodeError: 
            continue
        except Exception as e:
            logging.error(f"Erro crítico ao processar {file_path} com encoding {enc}: {e}")
            raise
    raise ValueError("Não foi possível decodificar o arquivo com os encodings disponíveis.")

# ============================================================================
# GERENCIADOR DE DADOS SPED (Backend)
# ============================================================================
class SpedManager:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.cursor = self.conn.cursor()
        self.structure = {}
        self.original_file = None

    def get_column_names(self, reg_type, data_len):
        cols = SPED_LAYOUT.get(reg_type, [])
        if len(cols) >= data_len:
            return cols[:data_len]
        extra = [f"field_{i+1}" for i in range(len(cols), data_len)]
        return cols + extra

    def ensure_table_structure(self, reg_type, data_len):
        needed_cols = self.get_column_names(reg_type, data_len)
        if reg_type not in self.structure:
            self.structure[reg_type] = len(needed_cols)
            cols_sql = ", ".join([f'"{c}" TEXT' for c in needed_cols])
            self.cursor.execute(f"CREATE TABLE IF NOT EXISTS REG_{reg_type} (id_row INTEGER PRIMARY KEY, parent_id INTEGER, {cols_sql})")
        else:
            current_len = self.structure[reg_type]
            if len(needed_cols) > current_len:
                existing_cols = self.get_column_names(reg_type, current_len)
                new_cols = needed_cols[current_len:]
                for nc in new_cols:
                    try:
                        self.cursor.execute(f"ALTER TABLE REG_{reg_type} ADD COLUMN \"{nc}\" TEXT")
                    except sqlite3.OperationalError:
                        pass
                self.structure[reg_type] = len(needed_cols)

    def import_file(self, file_path, progress_callback=None):
        self.original_file = file_path
        self.structure = {}
        tables = self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        for table in tables:
            self.cursor.execute(f"DROP TABLE {table[0]}")
        
        lines = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f: 
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='latin-1') as f: 
                lines = f.readlines()

        total_lines = len(lines)
        batch_size = 5000
        
        last_ids = {'C100': 0, 'C500': 0, 'D100': 0, 'D500': 0, 'E110': 0, 'E210': 0, 'H005': 0}
        data_buffer = {}

        for idx, line in enumerate(lines):
            if idx % 500 == 0 and progress_callback:
                progress_callback(int((idx / total_lines) * 100))
                QApplication.processEvents()

            line = line.strip()
            if not line.startswith('|') or len(line) < 3: 
                continue
            
            parts = line.split('|')
            reg_type = parts[1]
            clean_data = parts[2:-1]

            self.ensure_table_structure(reg_type, len(clean_data))

            current_parent = 0
            if reg_type in['C170', 'C190', 'C110', 'C113', 'C120', 'C195', 'C197'] and last_ids['C100'] > 0:
                current_parent = last_ids['C100']
            elif reg_type in ['C590', 'C510'] and last_ids['C500'] > 0:
                current_parent = last_ids['C500']
            elif reg_type in['D190', 'D110'] and last_ids['D100'] > 0:
                current_parent = last_ids['D100']
            elif reg_type in ['D590', 'D510'] and last_ids['D500'] > 0:
                current_parent = last_ids['D500']
            elif reg_type in['E111', 'E112', 'E113', 'E116'] and last_ids['E110'] > 0:
                current_parent = last_ids['E110']
            elif reg_type in['E220', 'E230', 'E240', 'E250'] and last_ids['E210'] > 0:
                current_parent = last_ids['E210']
            elif reg_type in ['H010', 'H020'] and last_ids['H005'] > 0:
                current_parent = last_ids['H005']

            if reg_type in last_ids:
                last_ids[reg_type] = idx

            if reg_type not in data_buffer:
                data_buffer[reg_type] = []
            
            data_buffer[reg_type].append((idx, current_parent, *clean_data))

            if idx > 0 and idx % batch_size == 0:
                self._flush_buffer(data_buffer)
                data_buffer = {}

        self._flush_buffer(data_buffer)
        self.conn.commit()
        if progress_callback: 
            progress_callback(100)
        return sorted(list(self.structure.keys()))

    def _flush_buffer(self, buffer):
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
                self.cursor.executemany(f"INSERT INTO REG_{reg} VALUES ({placeholders})", normalized_rows)
            except Exception as e:
                print(f"Error inserting {reg}: {e}")

    def get_data(self, reg_type):
        try:
            return pd.read_sql_query(f"SELECT * FROM REG_{reg_type} ORDER BY id_row", self.conn)
        except:
            return pd.DataFrame()

    def save_changes(self, reg_type, row_id, col_name, new_value):
        try:
            self.cursor.execute(f"UPDATE REG_{reg_type} SET \"{col_name}\" = ? WHERE id_row = ?", (new_value, row_id))
            self.conn.commit()
        except Exception as e:
            print(f"Erro ao salvar: {e}")

    def fix_0200_spaces(self):
        try:
            tables = [t[0] for t in self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if 'REG_0200' not in tables:
                return 0, "O Registro 0200 não foi encontrado ou nenhum arquivo foi importado."
            
            self.conn.create_function("CLEAN_SPACES", 1, lambda x: " ".join(str(x).split()) if x else x)
            self.cursor.execute('UPDATE REG_0200 SET "DESCR_ITEM" = CLEAN_SPACES("DESCR_ITEM")')
            rows_affected = self.cursor.rowcount
            self.conn.commit()
            return rows_affected, None
        except Exception as e:
            return 0, f"Erro ao corrigir espaços: {str(e)}"

    def adjust_inventory(self, target_value_str):
        """ Recalcula H010 e atualiza H005 baseado em um valor alvo """
        try:
            t_str = target_value_str.strip().replace('R$', '').replace(' ', '')
            if ',' in t_str and '.' in t_str:
                t_str = t_str.replace('.', '').replace(',', '.')
            elif ',' in t_str:
                t_str = t_str.replace(',', '.')
            target_value = float(t_str)
        except ValueError:
            return False, "Valor digitado é inválido. Digite apenas números."

        tables = [t[0] for t in self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'REG_H005' not in tables or 'REG_H010' not in tables:
            return False, "Registros de Inventário (H005/H010) não encontrados no arquivo."

        h010_df = pd.read_sql_query('SELECT id_row, parent_id, "QTD", "VL_UNIT", "VL_ITEM" FROM REG_H010 ORDER BY id_row', self.conn)
        if h010_df.empty:
            return False, "Nenhum item de inventário (H010) encontrado."

        def to_float(val):
            if not val: return 0.0
            try:
                return float(str(val).replace('.', '').replace(',', '.'))
            except:
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
            
            if idx == len(h010_df) - 1:
                diff = target_value - new_total_sum
                new_item_val_rounded = round(diff, 2)
                
            new_total_sum += new_item_val_rounded
            
            qtd = row['QTD_f']
            new_unit_val = (new_item_val_rounded / qtd) if qtd > 0 else 0.0
            
            str_item = f"{new_item_val_rounded:.2f}".replace('.', ',')
            str_unit = f"{new_unit_val:.6f}".replace('.', ',')
            
            updates_h010.append((str_unit, str_item, row['id_row']))

        self.cursor.executemany('UPDATE REG_H010 SET "VL_UNIT" = ?, "VL_ITEM" = ? WHERE id_row = ?', updates_h010)

        parent_sums = {}
        for i, row in h010_df.iterrows():
            pid = row['parent_id']
            val = float(updates_h010[i][1].replace(',', '.'))
            parent_sums[pid] = parent_sums.get(pid, 0.0) + val
            
        updates_h005 = []
        for pid, ptotal in parent_sums.items():
            str_ptotal = f"{ptotal:.2f}".replace('.', ',')
            updates_h005.append((str_ptotal, pid))
            
        self.cursor.executemany('UPDATE REG_H005 SET "VL_INV" = ? WHERE id_row = ?', updates_h005)
        self.conn.commit()
        
        return True, f"Inventário ajustado com sucesso!\nValor Total: R$ {target_value:,.2f}\nItens Recalculados: {len(h010_df)}"

    def execute_sql(self, query):
        try:
            cleaned_query = query.strip().upper()
            if cleaned_query.startswith("SELECT") or cleaned_query.startswith("PRAGMA"):
                return pd.read_sql_query(query, self.conn), None
            else:
                cursor = self.conn.cursor()
                cursor.execute(query)
                rows_affected = cursor.rowcount
                self.conn.commit()
                return f"Comando executado! Linhas afetadas: {rows_affected}", None
        except Exception as e:
            return None, str(e)

    def generate_sped_string(self):
        real_counts = {}
        tables = self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'REG_%'").fetchall()
        for table in tables:
            t_name = table[0]
            reg_name = t_name.replace("REG_", "")
            if reg_name.startswith('9'): 
                continue
            qtd = self.cursor.execute(f"SELECT Count(*) FROM {t_name}").fetchone()[0]
            if qtd > 0: 
                real_counts[reg_name] = qtd

        real_counts['9001'] = 1
        real_counts['9990'] = 1
        real_counts['9999'] = 1

        all_rows = []
        for table in tables:
            t_name = table[0]
            reg_name = t_name.replace("REG_", "")
            cursor_info = self.conn.execute(f"PRAGMA table_info({t_name})")
            col_names = [i[1] for i in cursor_info.fetchall() if i[1] not in ['id_row', 'parent_id']]
            col_str = ", ".join([f'"{c}"' for c in col_names])
            rows = self.cursor.execute(f"SELECT id_row, {col_str} FROM {t_name}").fetchall()
            for row in rows:
                all_rows.append((row[0], reg_name, list(row[1:])))
        
        all_rows.sort(key=lambda x: x[0])

        lines = []
        buffer_b9 = []
        types_processed = set()
        original_9990_count = None

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
                    original_9990_count = int(data[0])
                except: 
                    original_9990_count = 0

                missing = set(real_counts.keys()) - types_processed
                if '9900' in missing: 
                    missing.remove('9900')
                has_9900_ref = '9900' in types_processed
                
                for m in sorted(missing):
                    buffer_b9.append(f"|9900|{m}|{real_counts[m]}|")
                if not has_9900_ref:
                    buffer_b9.append("|9900|9900|__QTD_9900__|")

                count_9900_lines = sum(1 for l in buffer_b9 if l.startswith("|9900|"))
                final_b9 = []
                for b_line in buffer_b9:
                    if "__QTD_9900__" in b_line:
                        final_b9.append(b_line.replace("__QTD_9900__", str(count_9900_lines)))
                    else:
                        final_b9.append(b_line)
                
                lines.extend(final_b9)
                calculated_count = len(final_b9) + 1
                final_count = original_9990_count if original_9990_count == calculated_count + 1 else calculated_count
                lines.append(f"|9990|{final_count}|")

            elif reg == '9999':
                total_lines = len(lines) + 1
                lines.append(f"|9999|{total_lines}|")
            
            elif reg.startswith('9'):
                clean_data = [str(x) if x is not None else "" for x in data]
                buffer_b9.append(f"|{reg}|" + "|".join(clean_data) + "|")

        return "\n".join(lines) + "\n"

    def generate_cfop_analysis_pdf(self, output_dir: str) -> Tuple[int, str]:
        """Gera PDFs detalhados por CFOP baseado nos dados atuais no banco"""
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
                logging.info(f"PDF gerado para CFOP {cfop}: {pdf_path}")
            
            return count, f"Sucesso ao gerar {count} PDFs por CFOP"
        except Exception as e:
            logging.error(f"Erro ao gerar PDFs por CFOP: {e}")
            return 0, f"Erro: {str(e)}"

    def _draw_pdf_table(self, pdf: FPDF, records: List[SpedRecord]):
        """Desenha tabela de registros no PDF"""
        pdf.set_font("Arial", 'B', 10)
        header = ["CFOP", "Nota Fiscal", "Valor Oper.", "Base ICMS", "Alíquota", "Valor ICMS"]
        col_widths = [25, 35, 45, 45, 30, 45]
        
        for i, h in enumerate(header):
            pdf.cell(col_widths[i], 10, h, border=1, align='C')
        pdf.ln()

        pdf.set_font("Arial", size=9)
        totals = defaultdict(float)
        
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPED Fiscal Editor Pro 2.4 - Versão Combinada")
        self.resize(1400, 900)
        self.manager = SpedManager()
        self.current_reg = None
        self.setup_ui()

    def setup_ui(self):
        menubar = self.menuBar()
        file = menubar.addMenu("Arquivo")
        file.addAction("Importar SPED", self.import_sped)
        file.addAction("Exportar SPED", self.export_sped)
        
        analysis = menubar.addMenu("Análise")
        analysis.addAction("Gerar Relatórios por CFOP (PDF)", self.generate_cfop_reports)
        analysis.addAction("Resumo por CFOP", self.show_cfop_summary)
        
        self.status_bar = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress)
        self.status_label = QLabel("Pronto.")
        self.status_bar.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)
        
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

        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)

        # Aba 1: Editor
        self.grid_w = QWidget()
        vbox = QVBoxLayout(self.grid_w)
        
        hbox_top = QHBoxLayout()
        self.lbl_info = QLabel("Nenhum arquivo carregado.")
        hbox_top.addWidget(self.lbl_info)
        
        btn_fix_0200 = QPushButton("Corrigir Espaços (0200)")
        btn_fix_0200.setToolTip("Remove espaços duplos ou em branco no início/fim da descrição.")
        btn_fix_0200.clicked.connect(self.fix_0200_action)
        hbox_top.addWidget(btn_fix_0200)

        btn_fix_h005 = QPushButton("Ajustar Inventário (H005/H010)")
        btn_fix_h005.setToolTip("Recalcula itens do inventário para atingir o valor exato desejado.")
        btn_fix_h005.clicked.connect(self.fix_inventory_action)
        hbox_top.addWidget(btn_fix_h005)
        
        vbox.addLayout(hbox_top)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self.on_cell_changed)
        vbox.addWidget(self.table)
        self.tabs.addTab(self.grid_w, "Editor de Registros")

        # Aba 2: Análise por CFOP
        self.cfop_w = QWidget()
        vbox_cfop = QVBoxLayout(self.cfop_w)
        vbox_cfop.addWidget(QLabel("Análise de CFOP - Entradas"))
        self.table_cfop_entrada = QTableWidget()
        vbox_cfop.addWidget(self.table_cfop_entrada)
        vbox_cfop.addWidget(QLabel("Análise de CFOP - Saídas"))
        self.table_cfop_saida = QTableWidget()
        vbox_cfop.addWidget(self.table_cfop_saida)
        self.tabs.addTab(self.cfop_w, "Análise por CFOP")

        # Aba 3: SQL
        self.sql_w = QWidget()
        vbox_sql = QVBoxLayout(self.sql_w)
        vbox_sql.addWidget(QLabel("Consulta SQL"))
        self.txt_sql = QTextEdit()
        self.txt_sql.setMaximumHeight(100)
        vbox_sql.addWidget(self.txt_sql)
        btn_sql = QPushButton("Executar SQL")
        btn_sql.clicked.connect(self.run_sql)
        vbox_sql.addWidget(btn_sql)
        self.table_sql = QTableWidget()
        vbox_sql.addWidget(self.table_sql)
        self.tabs.addTab(self.sql_w, "Modo Avançado (SQL)")

    def update_progress(self, val):
        self.progress.setValue(val)

    def import_sped(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Abrir SPED", "", "Texto (*.txt);;Todos (*.*)")
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
            finally:
                self.progress.setVisible(False)

    def populate_tree(self, regs):
        self.tree.clear()
        blocks = {}
        for r in regs:
            blk_char = r[0]
            if blk_char not in blocks:
                p = QTreeWidgetItem(self.tree)
                p.setText(0, f"Bloco {blk_char}")
                blocks[blk_char] = p
            count = pd.read_sql_query(f"SELECT Count(*) FROM REG_{r}", self.manager.conn).iloc[0,0]
            child = QTreeWidgetItem(blocks[blk_char])
            child.setText(0, f"{r} ({count})")
            child.setData(0, Qt.ItemDataRole.UserRole, r)
        self.tree.expandAll()

    def filter_tree(self, text):
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

    def on_tree_click(self, item, col):
        reg = item.data(0, Qt.ItemDataRole.UserRole)
        if reg:
            self.current_reg = reg
            self.load_grid(reg)

    def load_grid(self, reg):
        self.status_label.setText(f"Carregando {reg}...")
        QApplication.processEvents()
        self.table.blockSignals(True)
        self.table.clear()
        df = self.manager.get_data(reg)
        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.blockSignals(False)
            self.status_label.setText("Tabela vazia.")
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
        
        self.lbl_info.setText(f"Editando: {reg} | Registros: {len(df)}")
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self.status_label.setText("Pronto.")

    def on_cell_changed(self, item):
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
            self.manager.save_changes(self.current_reg, row_id, col_name, item.text())

    def fix_0200_action(self):
        self.status_label.setText("Limpando espaços do Registro 0200...")
        QApplication.processEvents()
        rows_affected, err = self.manager.fix_0200_spaces()
        if err:
            QMessageBox.warning(self, "Aviso", err)
        else:
            QMessageBox.information(self, "Sucesso", f"Espaços corrigidos!\nProdutos afetados: {rows_affected}")
            if self.current_reg == '0200': 
                self.load_grid('0200')
        self.status_label.setText("Pronto.")

    def fix_inventory_action(self):
        text, ok = QInputDialog.getText(
            self, 
            "Ajustar Valor do Inventário", 
            "Digite o novo valor TOTAL do Inventário (H005):"
        )
        
        if ok and text.strip():
            self.status_label.setText("Recalculando inventário...")
            QApplication.processEvents()
            
            success, msg = self.manager.adjust_inventory(text)
            
            if not success:
                QMessageBox.warning(self, "Aviso", msg)
            else:
                QMessageBox.information(self, "Sucesso", msg)
                if self.current_reg in['H005', 'H010']:
                    self.load_grid(self.current_reg)
                    
            self.status_label.setText("Pronto.")

    def run_sql(self):
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
            self.table_sql.setHorizontalHeaderLabels(result.columns)
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

    def show_cfop_summary(self):
        """Mostra resumo de CFOPs na aba de análise"""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        try:
            data = process_sped_summary(self.manager.original_file)
            
            # Preencher tabela de entrada
            self.table_cfop_entrada.clear()
            self.table_cfop_entrada.setColumnCount(4)
            self.table_cfop_entrada.setHorizontalHeaderLabels(["CFOP", "Valor Total", "Base ICMS", "Valor ICMS"])
            self.table_cfop_entrada.setRowCount(len(data.cfop_entrada))
            
            row = 0
            for cfop in sorted(data.cfop_entrada.keys()):
                self.table_cfop_entrada.setItem(row, 0, QTableWidgetItem(cfop))
                self.table_cfop_entrada.setItem(row, 1, QTableWidgetItem(f"R$ {data.cfop_entrada[cfop]:,.2f}"))
                self.table_cfop_entrada.setItem(row, 2, QTableWidgetItem(f"R$ {data.icms_base_entrada[cfop]:,.2f}"))
                self.table_cfop_entrada.setItem(row, 3, QTableWidgetItem(f"R$ {data.icms_value_entrada[cfop]:,.2f}"))
                row += 1
            
            # Preencher tabela de saída
            self.table_cfop_saida.clear()
            self.table_cfop_saida.setColumnCount(4)
            self.table_cfop_saida.setHorizontalHeaderLabels(["CFOP", "Valor Total", "Base ICMS", "Valor ICMS"])
            self.table_cfop_saida.setRowCount(len(data.cfop_saida))
            
            row = 0
            for cfop in sorted(data.cfop_saida.keys()):
                self.table_cfop_saida.setItem(row, 0, QTableWidgetItem(cfop))
                self.table_cfop_saida.setItem(row, 1, QTableWidgetItem(f"R$ {data.cfop_saida[cfop]:,.2f}"))
                self.table_cfop_saida.setItem(row, 2, QTableWidgetItem(f"R$ {data.icms_base_saida[cfop]:,.2f}"))
                self.table_cfop_saida.setItem(row, 3, QTableWidgetItem(f"R$ {data.icms_value_saida[cfop]:,.2f}"))
                row += 1
            
            self.tabs.setCurrentWidget(self.cfop_w)
            self.status_label.setText("Resumo de CFOPs carregado.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao processar CFOPs: {str(e)}")

    def generate_cfop_reports(self):
        """Gera PDFs detalhados por CFOP"""
        if not self.manager.original_file:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo carregado.")
            return
        
        output_dir = QFileDialog.getExistingDirectory(self, "Selecione pasta para salvar os relatórios")
        if not output_dir:
            return
        
        self.status_label.setText("Gerando relatórios por CFOP...")
        QApplication.processEvents()
        
        count, msg = self.manager.generate_cfop_analysis_pdf(output_dir)
        if count > 0:
            QMessageBox.information(self, "Sucesso", f"{msg}\nPastas: {output_dir}")
            self._open_file(output_dir)
        else:
            QMessageBox.warning(self, "Aviso", msg)
        
        self.status_label.setText("Pronto.")

    def export_sped(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Salvar SPED", "Sped_Editado.txt", "Texto (*.txt)")
        if fname:
            self.status_label.setText("Exportando...")
            QApplication.processEvents()
            try:
                txt = self.manager.generate_sped_string()
                with open(fname, 'w', encoding='latin-1') as f: 
                    f.write(txt)
                QMessageBox.information(self, "Sucesso", "Arquivo exportado!\nBlocos foram recalculados.")
                self.status_label.setText("Exportação concluída.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))

    def _open_file(self, path: str):
        """Abre arquivo/pasta no explorador"""
        try:
            if sys.platform == "win32":
                os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            logging.error(f"Não foi possível abrir {path}: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
