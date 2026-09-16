"""
Módulo de exportação de dados SPED para Excel/CSV.
"""

import os
import csv
import logging
from typing import Optional, List

import pandas as pd

logger = logging.getLogger(__name__)


def export_to_csv(
    conn,
    reg_type: str,
    output_path: str,
    encoding: str = 'utf-8'
) -> tuple[bool, str]:
    """
    Exporta registros de um tipo específico para CSV.
    
    Args:
        conn: Conexão SQLite
        reg_type: Tipo de registro (ex: "C100")
        output_path: Caminho do arquivo de saída
        encoding: Encoding do arquivo (padrão: utf-8)
    
    Returns:
        Tuple (sucesso, mensagem)
    """
    try:
        df = pd.read_sql_query(
            f"SELECT * FROM REG_{reg_type} ORDER BY id_row",
            conn
        )
        if df.empty:
            return False, f"Nenhum registro encontrado para {reg_type}"
        
        df.to_csv(output_path, index=False, encoding=encoding)
        logger.info(f"CSV exportado: {output_path} ({len(df)} registros)")
        return True, f"Sucesso: {len(df)} registros exportados para {os.path.basename(output_path)}"
    except Exception as e:
        logger.error(f"Erro ao exportar CSV: {e}")
        return False, f"Erro ao exportar: {str(e)}"


def export_to_excel(
    conn,
    reg_type: str,
    output_path: str,
    sheet_name: Optional[str] = None
) -> tuple[bool, str]:
    """
    Exporta registros de um tipo específico para Excel.
    
    Args:
        conn: Conexão SQLite
        reg_type: Tipo de registro (ex: "C100")
        output_path: Caminho do arquivo de saída
        sheet_name: Nome da aba (padrão: nome do registro)
    
    Returns:
        Tuple (sucesso, mensagem)
    """
    try:
        df = pd.read_sql_query(
            f"SELECT * FROM REG_{reg_type} ORDER BY id_row",
            conn
        )
        if df.empty:
            return False, f"Nenhum registro encontrado para {reg_type}"
        
        sheet = sheet_name or reg_type
        df.to_excel(output_path, index=False, sheet_name=sheet)
        logger.info(f"Excel exportado: {output_path} ({len(df)} registros)")
        return True, f"Sucesso: {len(df)} registros exportados para {os.path.basename(output_path)}"
    except Exception as e:
        logger.error(f"Erro ao exportar Excel: {e}")
        return False, f"Erro ao exportar: {str(e)}"


def export_all_to_excel(
    conn,
    structure: dict,
    output_path: str
) -> tuple[bool, str]:
    """
    Exporta TODOS os tipos de registro para um único arquivo Excel (uma aba por registro).
    
    Args:
        conn: Conexão SQLite
        structure: Dicionário {reg_type: num_cols}
        output_path: Caminho do arquivo de saída
    
    Returns:
        Tuple (sucesso, mensagem)
    """
    try:
        total_registros = 0
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for reg_type in sorted(structure.keys()):
                try:
                    df = pd.read_sql_query(
                        f"SELECT * FROM REG_{reg_type} ORDER BY id_row",
                        conn
                    )
                    if not df.empty:
                        # Excel tem limite de 31 caracteres no nome da aba
                        sheet_name = reg_type[:31]
                        df.to_excel(writer, index=False, sheet_name=sheet_name)
                        total_registros += len(df)
                except Exception as e:
                    logger.warning(f"Aviso ao exportar {reg_type}: {e}")
        
        logger.info(f"Excel completo exportado: {output_path}")
        return True, f"Sucesso: {total_registros} registros em {len(structure)} abas exportados"
    except Exception as e:
        logger.error(f"Erro ao exportar Excel completo: {e}")
        return False, f"Erro ao exportar: {str(e)}"


def export_all_to_csv(
    conn,
    structure: dict,
    output_dir: str,
    encoding: str = 'utf-8'
) -> tuple[bool, str]:
    """
    Exporta TODOS os tipos de registro para arquivos CSV separados.
    
    Args:
        conn: Conexão SQLite
        structure: Dicionário {reg_type: num_cols}
        output_dir: Diretório de saída
        encoding: Encoding dos arquivos
    
    Returns:
        Tuple (sucesso, mensagem)
    """
    try:
        total_registros = 0
        arquivos_criados = []
        
        for reg_type in sorted(structure.keys()):
            try:
                df = pd.read_sql_query(
                    f"SELECT * FROM REG_{reg_type} ORDER BY id_row",
                    conn
                )
                if not df.empty:
                    filename = f"SPED_{reg_type}.csv"
                    filepath = os.path.join(output_dir, filename)
                    df.to_csv(filepath, index=False, encoding=encoding)
                    total_registros += len(df)
                    arquivos_criados.append(filename)
            except Exception as e:
                logger.warning(f"Aviso ao exportar {reg_type}: {e}")
        
        logger.info(f"CSVs exportados: {len(arquivos_criados)} arquivos em {output_dir}")
        return True, f"Sucesso: {len(arquivos_criados)} arquivos CSV criados ({total_registros} registros total)"
    except Exception as e:
        logger.error(f"Erro ao exportar CSVs: {e}")
        return False, f"Erro ao exportar: {str(e)}"
