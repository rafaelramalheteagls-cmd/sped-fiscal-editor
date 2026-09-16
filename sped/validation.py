"""
Módulo de Validação Fiscal do SPED.
Implementa regras de validação compatíveis com o PVA da SEFAZ.

Referências:
- Guia Prático da EFD ICMS/IPI
- Ato COTEPE ICMS 09/08
- PVA EFD ICMS/IPI versão 4.0

NOTA: No banco SQLite, os registros têm a seguinte estrutura:
- Coluna 0: id_row (auto-increment)
- Coluna 1: parent_id
- Coluna 2+: campos do registro SPED (conforme SPED_LAYOUT)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# Offset para converter índice do banco para índice do registro SPED
# No banco: [id_row, parent_id, campo1, campo2, ...]
# No SPED:  [campo1, campo2, ...]
# Então: indice_registro = indice_banco - 2

DB_OFFSET = 2  # id_row + parent_id


class Severity(Enum):
    """Severidade da validação"""
    ERROR = "ERRO"
    WARNING = "ADVERTÊNCIA"
    INFO = "INFORMAÇÃO"


@dataclass
class ValidationIssue:
    """Problema encontrado na validação"""
    severity: Severity
    code: str
    message: str
    record: str = ""
    field: str = ""
    line: int = 0
    
    def __str__(self):
        location = f" [Linha {self.line}]" if self.line else ""
        record_info = f" ({self.record})" if self.record else ""
        field_info = f" - Campo {self.field}" if self.field else ""
        return f"[{self.severity.value}] {self.code}: {self.message}{record_info}{field_info}{location}"


@dataclass
class ValidationResult:
    """Resultado da validação"""
    issues: List[ValidationIssue] = field(default_factory=list)
    total_records: int = 0
    records_validated: int = 0
    
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def summary(self) -> str:
        return (
            f"Validação concluída: {len(self.errors)} erro(s), "
            f"{len(self.warnings)} advertência(s) em {self.total_records} registros"
        )


# ============================================================================
# TABELAS DE REFERÊNCIA (conforme Tabela B do Ato COTEPE ICMS 09/08)
# ============================================================================

# CST ICMS válidos - Tabela B completa
# Fonte: Ato COTEPE/ICMS nº 09, de 18 de abril de 2008
CST_ICMS_VALIDOS = {
    # Tributado integralmente
    '000', '010', '020', '030', '040', '041', '050', '051', '060', '070', '090',
    # Substituição Tributária
    '100', '110', '112', '113', '115', '116', '120', '130', '135', '140', '141', '150', '151', '160', '170', '180', '190', '191', '192', '193', '194', '195',
    # Desonerado
    '200', '205', '210', '220', '230', '240', '241', '250', '251', '252', '253', '254', '255',
    # Isento
    '300', '310',
    # Não tributado
    '400', '410', '411', '412', '413', '414', '415', '416', '420', '430', '450', '460', '470', '490',
    # Com suspensão
    '500', '510',
    # Diferido
    '600', '610',
    # Operações com BC de ICMS zero
    '700', '710', '720', '730', '731', '732', '733', '734', '735', '736', '737', '738', '750', '751',
    # Outras operações de saída
    '800', '810',
    # Regime especial
    '900', '910', '920', '990'
}
CST_IPI_VALIDOS = {'00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '49', '50', '51', '52', '53', '54', '55', '99'}
CST_PIS_VALIDOS = {'01', '02', '03', '04', '05', '06', '07', '08', '09', '49', '50', '51', '52', '53', '54', '55', '56', '60', '61', '62', '63', '64', '65', '66', '67', '70', '73', '74', '75', '98', '99'}
CST_COFINS_VALIDOS = CST_PIS_VALIDOS

COD_SIT_VALIDOS = {
    '00': 'Documento regular',
    '01': 'Documento cancelado',
    '02': 'Documento inteiromente escrito em papel',
    '03': 'Documento cancelado por ingestão',
    '04': 'NFD - Nota Fiscal de Devolução',
    '05': 'Mercadoria recebida para demonstração',
    '06': 'Mercadoria recebida para dépósito em armazém',
    '07': 'Mercadoria recebida para conserto/reparo',
    '08': 'Documento fiscal emitido com base em regime especial',
    '09': 'Operação anulada',
    '10': 'Documento inutilizado',
    '99': 'Outra situação documental'
}

MODELOS_VALIDOS = ['01', '1A', '02', '2D', '2F', '04', '06', '07', '08', '09', '10', '11', '13', '14', '15', '16', '18', '21', '22', '24', '25', '26', '27', '28', '55', '65']


class SpedValidator:
    """Validador de arquivos SPED Fiscal."""
    
    def __init__(self):
        self.data: Dict[str, List[list]] = {}
    
    def load_data(self, conn) -> None:
        """Carrega dados do banco para validação."""
        import pandas as pd
        
        cursor = conn.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'REG_%'"
        ).fetchall()
        
        for table in tables:
            t_name = table[0]
            reg_type = t_name.replace("REG_", "")
            df = pd.read_sql_query(f"SELECT * FROM {t_name} ORDER BY id_row", conn)
            if not df.empty:
                self.data[reg_type] = df.values.tolist()
    
    def validate(self) -> ValidationResult:
        """Executa todas as validações."""
        result = ValidationResult()
        
        for reg_type, records in self.data.items():
            result.total_records += len(records)
        
        result.issues.extend(self._validate_required_records())
        result.issues.extend(self._validate_c100())
        result.issues.extend(self._validate_c170())
        result.issues.extend(self._validate_c190())
        result.issues.extend(self._validate_e110())
        result.issues.extend(self._validate_0200())
        result.issues.extend(self._validate_c100_c170_consistency())
        
        result.records_validated = result.total_records
        logger.info(result.summary)
        return result
    
    def _validate_required_records(self) -> List[ValidationIssue]:
        """Valida registros obrigatórios."""
        issues = []
        required = ['0000', '0001', '9990', '9999']
        
        for reg in required:
            if reg not in self.data:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="INT-001",
                    message=f"Registro {reg} obrigatório não encontrado",
                    record=reg
                ))
        
        if 'C100' in self.data and 'C001' not in self.data:
            issues.append(ValidationIssue(
                severity=Severity.ERROR,
                code="INT-002",
                message="Registro C001 obrigatório quando existe bloco C",
                record="C001"
            ))
        
        return issues
    
    def _validate_c100(self) -> List[ValidationIssue]:
        """
        Valida registros C100 (Documento Fiscal).
        
        Layout C100 no SPED:
        [0] IND_OPER, [1] IND_EMIT, [2] COD_PART, [3] COD_MOD, [4] COD_SIT,
        [5] SER, [6] NUM_DOC, [7] CHV_NFE, [8] DT_DOC, [9] DT_E_S,
        [10] VL_DOC, [11] IND_PGTO, [12] VL_DESC, ...
        
        No banco (após DB_OFFSET):
        record[2+0]=IND_OPER, record[2+1]=IND_EMIT, record[2+2]=COD_PART, etc.
        """
        issues = []
        if 'C100' not in self.data:
            return issues
        
        for idx, record in enumerate(self.data['C100']):
            line = idx + 1
            
            # Verificar se tem campos suficientes (2 de controle + 28 do C100)
            if len(record) < 2 + 20:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C100-001",
                    message="Registro C100 com número insuficiente de campos",
                    record="C100", line=line
                ))
                continue
            
            # Campos do C100 (offset por DB_OFFSET)
            ind_oper = str(record[2 + 0]) if record[2 + 0] else ""   # IND_OPER
            ind_emit = str(record[2 + 1]) if record[2 + 1] else ""   # IND_EMIT
            cod_mod = str(record[2 + 3]) if record[2 + 3] else ""    # COD_MOD
            cod_sit = str(record[2 + 4]) if record[2 + 4] else ""    # COD_SIT
            ser = str(record[2 + 5]) if record[2 + 5] else ""        # SER
            num_doc = str(record[2 + 6]) if record[2 + 6] else ""    # NUM_DOC
            chv_nfe = str(record[2 + 7]) if record[2 + 7] else ""    # CHV_NFE
            dt_doc = str(record[2 + 8]) if record[2 + 8] else ""     # DT_DOC
            
            # Validar IND_OPER
            if ind_oper not in ('0', '1'):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C100-002",
                    message=f"IND_OPER inválido: '{ind_oper}'. Deve ser 0 (Entrada) ou 1 (Saída)",
                    record="C100", field="IND_OPER", line=line
                ))
            
            # Validar IND_EMIT
            if ind_emit not in ('0', '1'):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C100-003",
                    message=f"IND_EMIT inválido: '{ind_emit}'. Deve ser 0 (Própria) ou 1 (Terceiros)",
                    record="C100", field="IND_EMIT", line=line
                ))
            
            # Validar COD_MOD
            if cod_mod and cod_mod not in MODELOS_VALIDOS:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C100-004",
                    message=f"COD_MOD inválido: '{cod_mod}'",
                    record="C100", field="COD_MOD", line=line
                ))
            
            # Validar COD_SIT
            if cod_sit and cod_sit not in COD_SIT_VALIDOS:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C100-005",
                    message=f"COD_SIT inválido: '{cod_sit}'",
                    record="C100", field="COD_SIT", line=line
                ))
            
            # Validar CHV_NFE para NF-e (modelos 55 e 65)
            if cod_mod in ('55', '65') and cod_sit == '00':
                if not chv_nfe or len(chv_nfe) != 44:
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        code="C100-006",
                        message=f"CHV_NFE inválida para NF-e: deve ter 44 dígitos (atual: {len(chv_nfe) if chv_nfe else 0})",
                        record="C100", field="CHV_NFE", line=line
                    ))
            
            # Validar formato da data (ddmmaaaa)
            if dt_doc and not self._validate_date(dt_doc):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C100-007",
                    message=f"DT_DOC com formato inválido: '{dt_doc}'. Esperado: ddmmaaaa",
                    record="C100", field="DT_DOC", line=line
                ))
        
        return issues
    
    def _validate_c170(self) -> List[ValidationIssue]:
        """
        Valida registros C170 (Itens do Documento).
        
        Layout C170 no SPED:
        [0] NUM_ITEM, [1] COD_ITEM, [2] DESCR_COMPL, [3] QTD, [4] UNID,
        [5] VL_ITEM, [6] VL_DESC, [7] IND_MOV, [8] CST_ICMS, [9] CFOP,
        [10] COD_NAT, [11] VL_BC_ICMS, [12] ALIQ_ICMS, [13] VL_ICMS, ...
        """
        issues = []
        if 'C170' not in self.data:
            return issues
        
        for idx, record in enumerate(self.data['C170']):
            line = idx + 1
            
            if len(record) < 2 + 14:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C170-001",
                    message="Registro C170 com número insuficiente de campos",
                    record="C170", line=line
                ))
                continue
            
            # Campos do C170 (offset por DB_OFFSET)
            num_item = str(record[2 + 0]) if record[2 + 0] else ""   # NUM_ITEM
            cod_item = str(record[2 + 1]) if record[2 + 1] else ""   # COD_ITEM
            qtd = str(record[2 + 3]) if record[2 + 3] else "0"       # QTD
            vl_item = str(record[2 + 5]) if record[2 + 5] else "0"   # VL_ITEM
            cst_icms = str(record[2 + 8]) if record[2 + 8] else ""   # CST_ICMS
            cfop = str(record[2 + 9]) if record[2 + 9] else ""       # CFOP
            aliq_icms = str(record[2 + 12]) if record[2 + 12] else "0"  # ALIQ_ICMS
            
            # Validar CFOP
            if cfop and not self._validate_cfop(cfop):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C170-002",
                    message=f"CFOP inválido: '{cfop}'",
                    record="C170", field="CFOP", line=line
                ))
            
            # Validar CST_ICMS
            if cst_icms and cst_icms not in CST_ICMS_VALIDOS:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C170-003",
                    message=f"CST_ICMS inválido: '{cst_icms}'",
                    record="C170", field="CST_ICMS", line=line
                ))
            
            # Validar COD_ITEM não vazio
            if not cod_item.strip():
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C170-004",
                    message="COD_ITEM vazio",
                    record="C170", field="COD_ITEM", line=line
                ))
            
            # Validar QTD positiva
            qtd_float = self._parse_float(qtd)
            if qtd_float < 0:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C170-005",
                    message=f"QTD com valor negativo: {qtd}",
                    record="C170", field="QTD", line=line
                ))
            
            # Validar VL_ITEM positivo
            vl_item_float = self._parse_float(vl_item)
            if vl_item_float < 0:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C170-006",
                    message=f"VL_ITEM com valor negativo: {vl_item}",
                    record="C170", field="VL_ITEM", line=line
                ))
            
            # Validar ALIQ_ICMS
            aliq_float = self._parse_float(aliq_icms)
            if aliq_float < 0 or aliq_float > 100:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C170-007",
                    message=f"ALIQ_ICMS fora do range válido: {aliq_float}%",
                    record="C170", field="ALIQ_ICMS", line=line
                ))
        
        return issues
    
    def _validate_c190(self) -> List[ValidationIssue]:
        """
        Valida registros C190 (Consolidação de Notas Fiscais).
        
        Layout C190 no SPED:
        [0] CST_ICMS, [1] CFOP, [2] ALIQ_ICMS, [3] VL_OPR, [4] VL_BC_ICMS,
        [5] VL_ICMS, [6] VL_BC_ICMS_ST, [7] VL_ICMS_ST, [8] VL_RED_BC,
        [9] VL_IPI, [10] COD_OBS
        """
        issues = []
        if 'C190' not in self.data:
            return issues
        
        for idx, record in enumerate(self.data['C190']):
            line = idx + 1
            
            if len(record) < 2 + 8:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C190-001",
                    message="Registro C190 com número insuficiente de campos",
                    record="C190", line=line
                ))
                continue
            
            # Campos do C190 (offset por DB_OFFSET)
            cst_icms = str(record[2 + 0]) if record[2 + 0] else ""    # CST_ICMS
            cfop = str(record[2 + 1]) if record[2 + 1] else ""        # CFOP
            aliq_icms = str(record[2 + 2]) if record[2 + 2] else "0"  # ALIQ_ICMS
            vl_opr = str(record[2 + 3]) if record[2 + 3] else "0"     # VL_OPR
            vl_bc_icms = str(record[2 + 4]) if record[2 + 4] else "0" # VL_BC_ICMS
            vl_icms = str(record[2 + 5]) if record[2 + 5] else "0"    # VL_ICMS
            
            # Validar CST_ICMS
            if cst_icms not in CST_ICMS_VALIDOS:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C190-002",
                    message=f"CST_ICMS inválido: '{cst_icms}'",
                    record="C190", field="CST_ICMS", line=line
                ))
            
            # Validar CFOP
            if not self._validate_cfop(cfop):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="C190-003",
                    message=f"CFOP inválido: '{cfop}'",
                    record="C190", field="CFOP", line=line
                ))
            
            # Validar alíquota
            aliq_float = self._parse_float(aliq_icms)
            if aliq_float < 0 or aliq_float > 100:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C190-004",
                    message=f"ALIQ_ICMS fora do range: {aliq_float}%",
                    record="C190", field="ALIQ_ICMS", line=line
                ))
            
            # Validar coerência: VL_ICMS ≈ VL_BC_ICMS * ALIQ_ICMS / 100
            vl_bc = self._parse_float(vl_bc_icms)
            vl_icms_val = self._parse_float(vl_icms)
            
            if vl_bc > 0 and aliq_float > 0:
                expected_icms = vl_bc * (aliq_float / 100)
                diff = abs(expected_icms - vl_icms_val)
                if diff > 0.10:
                    issues.append(ValidationIssue(
                        severity=Severity.WARNING,
                        code="C190-005",
                        message=f"VL_ICMS ({vl_icms_val}) difere do calculado ({expected_icms:.2f})",
                        record="C190", field="VL_ICMS", line=line
                    ))
            
            # Validar VL_BC_ICMS <= VL_OPR (base não pode exceder operação)
            vl_opr_val = self._parse_float(vl_opr)
            if vl_bc > vl_opr_val and vl_opr_val > 0:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="C190-006",
                    message=f"VL_BC_ICMS ({vl_bc}) excede VL_OPR ({vl_opr_val})",
                    record="C190", field="VL_BC_ICMS", line=line
                ))
        
        return issues
    
    def _validate_e110(self) -> List[ValidationIssue]:
        """
        Valida registros E110 (Apuração do ICMS).
        
        Layout E110 no SPED:
        [0] VL_TOT_DEBITOS, [1] VL_AJ_DEBITOS, [2] VL_TOT_AJ_DEBITOS,
        [3] VL_ESTORNOS_CRED, [4] VL_TOT_CREDITOS, [5] VL_AJ_CREDITOS,
        [6] VL_TOT_AJ_CREDITOS, [7] VL_ESTORNOS_DEB, [8] VL_SLD_CREDOR_ANT,
        [9] VL_SLD_APURADO, [10] VL_TOT_DED, [11] VL_ICMS_RECOLHER,
        [12] VL_SLD_CREDOR_TRANSPORTAR, [13] DEB_ESP
        """
        issues = []
        if 'E110' not in self.data:
            return issues
        
        for idx, record in enumerate(self.data['E110']):
            line = idx + 1
            
            if len(record) < 2 + 10:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="E110-001",
                    message="Registro E110 com número insuficiente de campos",
                    record="E110", line=line
                ))
                continue
            
            # Campos do E110 (offset por DB_OFFSET)
            vl_tot_debitos = self._parse_float(record[2 + 0])
            vl_aj_debitos = self._parse_float(record[2 + 1])
            vl_tot_aj_debitos = self._parse_float(record[2 + 2])
            vl_estornos_cred = self._parse_float(record[2 + 3])
            vl_tot_creditos = self._parse_float(record[2 + 4])
            vl_aj_creditos = self._parse_float(record[2 + 5])
            vl_tot_aj_creditos = self._parse_float(record[2 + 6])
            vl_estornos_deb = self._parse_float(record[2 + 7])
            vl_sld_credor_ant = self._parse_float(record[2 + 8])
            vl_sld_apurado = self._parse_float(record[2 + 9])
            
            # Validar cálculo do saldo apurado
            total_debitos = vl_tot_debitos + vl_aj_debitos + vl_tot_aj_debitos - vl_estornos_cred
            total_creditos = vl_tot_creditos + vl_aj_creditos + vl_tot_aj_creditos - vl_estornos_deb
            sld_esperado = total_debitos - total_creditos + vl_sld_credor_ant
            
            diff = abs(sld_esperado - vl_sld_apurado)
            if diff > 0.01:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="E110-002",
                    message=f"VL_SLD_APURADO incorreto. Informado: {vl_sld_apurado}, Esperado: {sld_esperado:.2f}",
                    record="E110", field="VL_SLD_APURADO", line=line
                ))
        
        return issues
    
    def _validate_0200(self) -> List[ValidationIssue]:
        """
        Valida registros 0200 (Tabela de Identificação do Item).
        
        Layout 0200 no SPED:
        [0] COD_ITEM, [1] DESCR_ITEM, [2] COD_BARRA, [3] COD_ANT_ITEM,
        [4] UNID_INV, [5] TIPO_ITEM, [6] COD_NCM, [7] EX_IPI,
        [8] COD_GEN, [9] COD_LST, [10] ALIQ_ICMS, [11] CEST
        """
        issues = []
        if '0200' not in self.data:
            return issues
        
        cod_items_vistos = set()
        
        for idx, record in enumerate(self.data['0200']):
            line = idx + 1
            
            if len(record) < 2 + 6:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="0200-001",
                    message="Registro 0200 com número insuficiente de campos",
                    record="0200", line=line
                ))
                continue
            
            # Campos do 0200 (offset por DB_OFFSET)
            cod_item = str(record[2 + 0]) if record[2 + 0] else ""    # COD_ITEM
            descr_item = str(record[2 + 1]) if record[2 + 1] else ""  # DESCR_ITEM
            cod_ncm = str(record[2 + 6]) if record[2 + 6] else ""     # COD_NCM
            
            # Verificar duplicidade
            if cod_item in cod_items_vistos:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    code="0200-002",
                    message=f"COD_ITEM duplicado: '{cod_item}'",
                    record="0200", field="COD_ITEM", line=line
                ))
            cod_items_vistos.add(cod_item)
            
            # Validar descrição
            if not descr_item.strip():
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="0200-003",
                    message=f"DESCR_ITEM vazio para item '{cod_item}'",
                    record="0200", field="DESCR_ITEM", line=line
                ))
            
            # Validar COD_NCM (8 dígitos)
            if cod_ncm and len(cod_ncm) != 8:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    code="0200-004",
                    message=f"COD_NCM com tamanho inválido: '{cod_ncm}' (esperado 8 dígitos)",
                    record="0200", field="COD_NCM", line=line
                ))
        
        return issues
    
    def _validate_c100_c170_consistency(self) -> List[ValidationIssue]:
        """Valida consistência entre C100 e C170 (pais e filhos)."""
        issues = []
        
        if 'C100' not in self.data or 'C170' not in self.data:
            return issues
        
        # Coletar IDs dos C100
        c100_ids = set()
        for record in self.data['C100']:
            if len(record) > 0:
                c100_ids.add(record[0])  # id_row
        
        # Verificar se todo C170 tem C100 pai
        for idx, record in enumerate(self.data['C170']):
            if len(record) > 1:
                parent_id = record[1]  # parent_id
                if parent_id and parent_id not in c100_ids:
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        code="C170-008",
                        message=f"C170 com parent_id={parent_id} não encontrado no C100",
                        record="C170", field="parent_id", line=idx + 1
                    ))
        
        return issues
    
    # ========================================================================
    # FUNÇÕES AUXILIARES
    # ========================================================================
    
    def _validate_date(self, date_str: str) -> bool:
        """Valida formato de data ddmmaaaa."""
        if not date_str or len(date_str) != 8:
            return False
        try:
            day = int(date_str[:2])
            month = int(date_str[2:4])
            year = int(date_str[4:8])
            return 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100
        except ValueError:
            return False
    
    def _validate_cfop(self, cfop: str) -> bool:
        """Valida CFOP (4 dígitos, 1000-9999)."""
        if not cfop or len(cfop) != 4:
            return False
        try:
            return 1000 <= int(cfop) <= 9999
        except ValueError:
            return False
    
    def _parse_float(self, value) -> float:
        """Converte valor para float."""
        if not value:
            return 0.0
        try:
            if isinstance(value, (int, float)):
                return float(value)
            return float(str(value).replace(',', '.'))
        except (ValueError, TypeError):
            return 0.0


def validate_sped(conn) -> ValidationResult:
    """Função principal de validação do SPED."""
    validator = SpedValidator()
    validator.load_data(conn)
    return validator.validate()
