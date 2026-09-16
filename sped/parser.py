"""
Módulo de parsing de arquivos SPED Fiscal.
Contém funções para processar e extrair dados de arquivos SPED.
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from collections import defaultdict

from .models import (
    ENCODINGS, VALID_RECORD_TYPES, ENTRADA_CFOPS_PREFIX,
    C100_NUM_DOC_IDX, C500_NUM_DOC_IDX, D100_NUM_DOC_IDX, D500_NUM_DOC_IDX,
    C190_CFOP_IDX, C190_ALIQ_ICMS_IDX, C190_VL_OPR_IDX,
    C190_VL_BC_ICMS_IDX, C190_VL_ICMS_IDX,
    C590_CFOP_IDX, C590_VL_OPR_IDX,
    D590_CFOP_IDX, D590_VL_OPR_IDX,
    SpedSummaryData, SpedRecord
)
from .utils import parse_float

logger = logging.getLogger(__name__)


def process_sped_summary(file_path: str) -> SpedSummaryData:
    """
    Processa arquivo SPED e retorna resumo por CFOP.
    
    Args:
        file_path: Caminho para o arquivo SPED
    
    Returns:
        SpedSummaryData com totais por CFOP
    
    Raises:
        ValueError: Se o arquivo não puder ser decodificado
        FileNotFoundError: Se o arquivo não existir
        PermissionError: Se não houver permissão de leitura
    """
    data = SpedSummaryData()
    for enc in ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc) as file:
                for line_num, line in enumerate(file, 1):
                    try:
                        fields = line.strip().split('|')
                        if len(fields) < 3:
                            continue
                        
                        reg_type = fields[1] if len(fields) > 1 else ""
                        
                        # Processar cada tipo de registro com seus próprios índices
                        if reg_type == 'C190' and len(fields) > C190_VL_ICMS_IDX:
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
                        
                        elif reg_type == 'C590' and len(fields) > C190_VL_ICMS_IDX:
                            cfop = fields[C590_CFOP_IDX]
                            valor = parse_float(fields[C590_VL_OPR_IDX])
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
                        
                        elif reg_type == 'D190' and len(fields) > C190_VL_ICMS_IDX:
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
                        
                        elif reg_type == 'D590' and len(fields) > C190_VL_ICMS_IDX:
                            cfop = fields[D590_CFOP_IDX]
                            valor = parse_float(fields[D590_VL_OPR_IDX])
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

def parse_cte_xml(xml_path: str) -> Dict[str, str]:
    """
    Parses CTE XML and extracts transportadora and relevant data.
    
    Args:
        xml_path: Caminho para o arquivo XML da CTE
    
    Returns:
        Dict with CNPJ, IE, xNome, RNTRC and other transportadora data
    """
    import xml.etree.ElementTree as ET
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Namespaces do CTE
        ns = {
            'cte': 'http://www.portalfiscal.inf.br/cte',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
        
        # Extrair dados do emit (transportadora)
        emit = root.find('.//cte:emit', ns)
        cnpj = ''
        ie = ''
        xnome = ''
        xlgr = ''
        nro = ''
        xbairro = ''
        cmun = ''
        xmun = ''
        cep = ''
        if emit is not None:
            cnpj_elem = emit.find('cte:CNPJ', ns)
            if cnpj_elem is not None and cnpj_elem.text:
                cnpj = cnpj_elem.text.strip()
            
            ie_elem = emit.find('cte:IE', ns)
            if ie_elem is not None and ie_elem.text:
                ie = ie_elem.text.strip()
            
            xnome_elem = emit.find('cte:xNome', ns)
            if xnome_elem is not None and xnome_elem.text:
                xnome = xnome_elem.text.strip()

            ender_emit = emit.find('cte:enderEmit', ns)
            if ender_emit is not None:
                xlgr_elem = ender_emit.find('cte:xLgr', ns)
                if xlgr_elem is not None and xlgr_elem.text:
                    xlgr = xlgr_elem.text.strip()

                nro_elem = ender_emit.find('cte:nro', ns)
                if nro_elem is not None and nro_elem.text:
                    nro = nro_elem.text.strip()

                xbairro_elem = ender_emit.find('cte:xBairro', ns)
                if xbairro_elem is not None and xbairro_elem.text:
                    xbairro = xbairro_elem.text.strip()

                cmun_elem = ender_emit.find('cte:cMun', ns)
                if cmun_elem is not None and cmun_elem.text:
                    cmun = cmun_elem.text.strip()

                xmun_elem = ender_emit.find('cte:xMun', ns)
                if xmun_elem is not None and xmun_elem.text:
                    xmun = xmun_elem.text.strip()

                cep_elem = ender_emit.find('cte:CEP', ns)
                if cep_elem is not None and cep_elem.text:
                    cep = cep_elem.text.strip()
        
        # Extrair RNTRC da infModal (irmão de infCarga dentro de infCTeNorm)
        rntrc = ''
        inf_modal = root.find('.//cte:infModal', ns)
        if inf_modal is not None:
            rodo = inf_modal.find('cte:rodo', ns)
            if rodo is not None:
                rntrc_elem = rodo.find('cte:RNTRC', ns)
                if rntrc_elem is not None and rntrc_elem.text:
                    rntrc = rntrc_elem.text.strip()
        
        # Extrair vPrest (valor do servico) da vPrest
        vprest_elem = root.find('.//cte:vPrest', ns)
        vprest = 0.0
        if vprest_elem is not None:
            vtPrest_elem = vprest_elem.find('cte:vTPrest', ns)
            if vtPrest_elem is not None and vtPrest_elem.text:
                try:
                    vprest = float(vtPrest_elem.text)
                except ValueError:
                    vprest = 0.0
        
        # Extrair chave de acesso do CT-e (Id="CTE<chave>" no infCte)
        chv_cte = ''
        inf_cte = root.find('.//cte:infCte', ns)
        if inf_cte is not None:
            cte_id = (inf_cte.get('Id') or '').strip()
            if cte_id.upper().startswith('CTE') and len(cte_id) == 47:
                chv_cte = cte_id[3:]

        # Extrair numero do CT-e (nCT no campo ide, usado em NUM_DOC do D100)
        nct = ''
        serie = ''
        dh_emi = ''
        cfop = ''
        cmun_ini = ''
        cmun_fim = ''
        modal = ''
        ide = root.find('.//cte:infCte/cte:ide', ns)
        if ide is None:
            ide = root.find('.//cte:ide', ns)
        if ide is not None:
            nct_elem = ide.find('cte:nCT', ns)
            if nct_elem is not None and nct_elem.text:
                nct = nct_elem.text.strip()

            serie_elem = ide.find('cte:serie', ns)
            if serie_elem is not None and serie_elem.text:
                serie = serie_elem.text.strip()

            dh_emi_elem = ide.find('cte:dhEmi', ns)
            if dh_emi_elem is not None and dh_emi_elem.text:
                dh_emi = dh_emi_elem.text.strip()

            cfop_elem = ide.find('cte:CFOP', ns)
            if cfop_elem is not None and cfop_elem.text:
                cfop = cfop_elem.text.strip()

            cmun_ini_elem = ide.find('cte:cMunIni', ns)
            if cmun_ini_elem is not None and cmun_ini_elem.text:
                cmun_ini = cmun_ini_elem.text.strip()

            cmun_fim_elem = ide.find('cte:cMunFim', ns)
            if cmun_fim_elem is not None and cmun_fim_elem.text:
                cmun_fim = cmun_fim_elem.text.strip()

            modal_elem = ide.find('cte:modal', ns)
            if modal_elem is not None and modal_elem.text:
                modal = modal_elem.text.strip()
        
        # Extrair dados do ideal (CNPJ/IE do destinatario, etc.)
        dest = root.find('.//cte:dest', ns)
        cnpj_dest = ''
        ie_dest = ''
        if dest is not None:
            cnpj_dest_elem = dest.find('cte:CNPJ', ns)
            if cnpj_dest_elem is not None and cnpj_dest_elem.text:
                cnpj_dest = cnpj_dest_elem.text.strip()
            
            ie_dest_elem = dest.find('cte:IE', ns)
            if ie_dest_elem is not None and ie_dest_elem.text:
                ie_dest = ie_dest_elem.text.strip()
        
        return {
            'cnpj': cnpj,
            'ie': ie,
            'xnome': xnome,
            'xlgr': xlgr,
            'nro': nro,
            'xbairro': xbairro,
            'cmun': cmun,
            'xmun': xmun,
            'cep': cep,
            'rntrc': rntrc,
            'chv_cte': chv_cte,
            'nct': nct,
            'serie': serie,
            'dh_emi': dh_emi,
            'cfop': cfop,
            'cmun_ini': cmun_ini,
            'cmun_fim': cmun_fim,
            'modal': modal,
            'cnpj_dest': cnpj_dest,
            'ie_dest': ie_dest,
            'vprest': vprest
        }
        
    except ET.ParseError as e:
        logger.error(f"Erro ao fazer parse do XML CTE: {e}")
        raise
    except FileNotFoundError:
        logger.error(f"Arquivo XML nao encontrado: {xml_path}")
        raise



def process_sped_detailed(file_path: str) -> Dict[str, List[SpedRecord]]:
    """
    Processa arquivo SPED e retorna registros detalhados por CFOP.
    
    Args:
        file_path: Caminho para o arquivo SPED
    
    Returns:
        Dicionário com CFOP como chave e lista de SpedRecord como valor
    
    Raises:
        ValueError: Se o arquivo não puder ser decodificado
        FileNotFoundError: Se o arquivo não existir
        PermissionError: Se não houver permissão de leitura
    """
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
                    if tipo_registro in ('C100', 'C500', 'D100', 'D500'):
                        try:
                            if tipo_registro == 'C100':
                                num_doc_idx = C100_NUM_DOC_IDX
                            elif tipo_registro == 'C500':
                                num_doc_idx = C500_NUM_DOC_IDX
                            elif tipo_registro == 'D500':
                                num_doc_idx = D500_NUM_DOC_IDX
                            else:
                                num_doc_idx = D100_NUM_DOC_IDX
                            nota_pai_atual = {
                                'tipo': tipo_registro,
                                'numero': fields[num_doc_idx] if len(fields) > num_doc_idx else "N/A"
                            }
                        except IndexError:
                            logger.warning(f"Linha {i}: Registro {tipo_registro} com campos insuficientes.")
                            nota_pai_atual = None
                    
                    # Processar registros de consolidação (C190, C590, D190, D590)
                    if tipo_registro in ('C190', 'C590', 'D190', 'D590'):
                        # Determinar tipo pai esperado
                        tipo_pai_esperado = None
                        if tipo_registro == 'C190':
                            tipo_pai_esperado = 'C100'
                        elif tipo_registro == 'C590':
                            tipo_pai_esperado = 'C500'
                        elif tipo_registro == 'D190':
                            tipo_pai_esperado = 'D100'
                        elif tipo_registro == 'D590':
                            tipo_pai_esperado = 'D500'
                        
                        # Processar se o pai corresponder ou não tiver pai
                        if nota_pai_atual is None or nota_pai_atual['tipo'] == tipo_pai_esperado:
                            try:
                                # Usar índices corretos para cada tipo de registro
                                if tipo_registro in ('C190', 'C590', 'D190', 'D590'):
                                    # Todos têm mesma estrutura: CST|CFOP|ALIQ|VL_OPR|BC_ICMS|VL_ICMS
                                    cfop_idx = C190_CFOP_IDX
                                    vl_opr_idx = C190_VL_OPR_IDX
                                    vl_bc_icms_idx = C190_VL_BC_ICMS_IDX
                                    vl_icms_idx = C190_VL_ICMS_IDX
                                    aliq_idx = C190_ALIQ_ICMS_IDX
                                
                                # Verificar se tem campos suficientes
                                max_idx = max(cfop_idx, vl_opr_idx, vl_bc_icms_idx, vl_icms_idx, aliq_idx)
                                if len(fields) > max_idx:
                                    cfop = fields[cfop_idx]
                                    # Usar número do documento do pai ou "N/A"
                                    numero_doc = nota_pai_atual['numero'] if nota_pai_atual else "N/A"
                                    tipo_pai = nota_pai_atual['tipo'] if nota_pai_atual else tipo_pai_esperado
                                    
                                    record = SpedRecord(
                                        line_number=i,
                                        tipo_registro_pai=tipo_pai,
                                        numero_doc=numero_doc,
                                        cfop=cfop,
                                        aliquota=parse_float(fields[aliq_idx]),
                                        valor_operacao=parse_float(fields[vl_opr_idx]),
                                        base_icms=parse_float(fields[vl_bc_icms_idx]),
                                        valor_icms=parse_float(fields[vl_icms_idx])
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
