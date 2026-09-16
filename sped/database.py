"""

Módulo de gerenciamento de banco de dados SPED.

Contém o SpedManager para operações com SQLite.

"""



import re

import sqlite3

import logging

import xml.etree.ElementTree as ET

from datetime import datetime

from datetime import timedelta

from typing import Dict, List, Optional, Tuple, Union

from contextlib import contextmanager



import pandas as pd



from .parser import parse_cte_xml

from .models import SPED_LAYOUT, CHILD_RECORDS_MAP

from .utils import sanitize_reg_type

from .history import EditHistory, EditOperation


# Mapeia CFOP de prestação de serviço de transporte (6xxx) para a aquisição
# correspondente (1xxx/2xxx/3xxx). Usado ao importar CT-e como entrada.
CFOP_TRANSPORTE_ENTRADA = {
    '5351': '1351', '5352': '1352', '5353': '1353', '5354': '1354',
    '5355': '1355', '5356': '1356', '5357': '1357', '5358': '1358',
    '5359': '1359', '5360': '1360',
    '6351': '1351', '6352': '1352', '6353': '1353', '6354': '1354',
    '6355': '1355', '6356': '1356', '6357': '1357', '6358': '1358',
    '6359': '1359', '6360': '1360',
    '6932': '1352', '6931': '1351', '6933': '1353', '6934': '1354',
    '6935': '1355', '6936': '1356', '6937': '1357', '6949': '1949',
    '7358': '1358', '7360': '1360',
}



logger = logging.getLogger(__name__)





class SpedManager:

    """Gerenciador principal de dados SPED com SQLite."""

    

    def __init__(self) -> None:

        self._conn: sqlite3.Connection = sqlite3.connect(":memory:")

        self._cursor: sqlite3.Cursor = self._conn.cursor()

        self.structure: Dict[str, int] = {}

        self.original_file: Optional[str] = None

        self._last_inserted_ids: Dict[str, int] = {}

        self._next_ids: Dict[str, int] = {}  # Próximo ID auto-increment para cada tabela

        self.history = EditHistory(max_size=200)

        

    @contextmanager

    def _transaction(self):

        """Context manager para transações SQLite."""

        try:

            yield self._cursor

            self._conn.commit()

        except Exception as e:

            self._conn.rollback()

            logger.error(f"Transação falhou: {e}")

            raise

    

    def close(self) -> None:

        """Fecha a conexão com o banco."""

        if self._conn:

            self._conn.close()

            logger.info("Conexão SQLite fechada.")

    

    def get_column_names(self, reg_type: str, data_len: int) -> List[str]:

        """Retorna nomes das colunas para um registro."""

        cols = SPED_LAYOUT.get(reg_type, [])

        if len(cols) >= data_len:

            return cols[:data_len]

        extra = [f"field_{i+1}" for i in range(len(cols), data_len)]

        return cols + extra

    

    def ensure_table_structure(self, reg_type: str, data_len: int) -> None:

        """Garante que a estrutura da tabela existe."""

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

        """Retorna o último ID inserido para um registro."""

        return self._last_inserted_ids.get(reg_type, 0)

    

    def _set_last_inserted_id(self, reg_type: str, row_id: int) -> None:

        """Define o último ID inserido para um registro."""

        self._last_inserted_ids[reg_type] = row_id

    

    def _peek_next_id(self, reg_type: str) -> int:

        """Retorna o próximo ID que será usado para um registro (sem incrementar)."""

        return self._next_ids.get(reg_type, 1)

    

    def _get_and_increment_next_id(self, reg_type: str) -> int:

        """Retorna o próximo ID e incrementa o contador."""

        current = self._next_ids.get(reg_type, 1)

        self._next_ids[reg_type] = current + 1

        return current

    

    def import_file(self, file_path: str, progress_callback=None) -> List[str]:

        """Importa arquivo SPED para o banco de dados."""

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

        

        data_buffer: Dict[str, List[tuple]] = {}

        # Rastrear idx do último registro pai encontrado por tipo

        parent_idx_map: Dict[str, int] = {}

        

        for idx, line in enumerate(lines):

            if idx % 500 == 0 and progress_callback:

                progress_callback(int((idx / total_lines) * 100))

            

            line = line.strip()

            if not line.startswith('|') or len(line) < 3:

                continue

            

            parts = line.split('|')

            if len(parts) < 3:

                continue

                

            reg_type = parts[1]

            clean_data = parts[2:-1]

            

            self.ensure_table_structure(reg_type, len(clean_data))

            

            # Verificar se este registro é filho de algum pai

            current_parent = 0

            for parent_type, child_types in CHILD_RECORDS_MAP.items():

                if reg_type in child_types and parent_type in parent_idx_map:

                    current_parent = parent_idx_map[parent_type]

                    break

            

            if reg_type not in data_buffer:

                data_buffer[reg_type] = []

            

            data_buffer[reg_type].append((idx, current_parent, *clean_data))

            

            # Se é um registro pai, armazenar seu idx

            for parent_type in CHILD_RECORDS_MAP:

                if reg_type == parent_type:

                    parent_idx_map[parent_type] = idx

                    break

            

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

        """Insere dados do buffer no banco."""

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

                # Buscar o último ID real inserido para esta tabela

                result = self._cursor.execute(

                    f"SELECT MAX(id_row) FROM REG_{reg}"

                ).fetchone()

                max_id = result[0] if result and result[0] else 0

                self._set_last_inserted_id(reg, max_id)

            except sqlite3.Error as e:

                logger.error(f"Erro ao inserir {reg}: {e}")

                raise

    

    def get_data(self, reg_type: str, limit: int = 10000, offset: int = 0) -> pd.DataFrame:

        """Retorna dados paginados de um registro."""

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

        """Retorna o total de linhas de um registro."""

        try:

            safe_reg = sanitize_reg_type(reg_type)

            result = self._cursor.execute(

                f"SELECT COUNT(*) FROM REG_{safe_reg}"

            ).fetchone()

            return result[0] if result else 0

        except (ValueError, sqlite3.Error) as e:

            logger.error(f"Erro ao contar linhas: {e}")

            return 0

    def _block_rank(self, reg_type: str) -> tuple:

        """Retorna (ordem_do_bloco, posicao_no_bloco) segundo o layout SPED.

        posicao_no_bloco: 0 = abertura do bloco, 1 = conteudo, 2 = fechamento.
        """

        if not reg_type:
            return (99, 1)
        first = reg_type[0]

        if first == '0':
            block = 10
        elif first == 'B':
            block = 15
        elif first == 'C':
            block = 20
        elif first == 'D':
            block = 30
        elif first == 'E':
            block = 40
        elif first == 'G':
            block = 50
        elif first == 'H':
            block = 60
        elif first == 'K':
            block = 70
        elif first == '1':
            block = 80
        elif first == '2':
            block = 85
        elif first == '9':
            block = 90
        else:
            block = 99

        # Posicao dentro do bloco: abertura (X001/X000), fechamento (X990), conteudo
        if reg_type in ('0000',) or reg_type.endswith('001'):
            pos = 0
        elif reg_type.endswith('990') or reg_type.endswith('9999') or reg_type.endswith('9990'):
            pos = 2
        else:
            pos = 1

        return (block, pos)

    def get_register_types(self) -> List[str]:

        """Retorna a lista ordenada de tipos de registro existentes no banco."""

        try:

            result = self._cursor.execute(

                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'REG_%'"

            ).fetchall()

            regs = [t[0][4:] for t in result]
            return sorted(regs)

        except sqlite3.Error as e:

            logger.error(f"Erro ao listar registros: {e}")

            return []

    

    def global_search(

        self, 

        search_term: str, 

        case_sensitive: bool = False,

        reg_types: Optional[List[str]] = None

    ) -> pd.DataFrame:

        """

        Busca global em todos os registros do SPED.

        

        Args:

            search_term: Termo de busca

            case_sensitive: Se a busca deve ser case-sensitive (padrão: False)

            reg_types: Lista de tipos de registro para buscar (padrão: todos)

        

        Returns:

            DataFrame com os resultados encontrados

        """

        if not search_term or not search_term.strip():

            return pd.DataFrame()

        

        try:

            tables = []

            if reg_types:

                for rt in reg_types:

                    try:

                        safe_reg = sanitize_reg_type(rt)

                        tables.append(f"REG_{safe_reg}")

                    except ValueError:

                        continue

            else:

                result = self._cursor.execute(

                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'REG_%'"

                ).fetchall()

                tables = [t[0] for t in result]

            

            if not tables:

                return pd.DataFrame()

            

            # Buscar em cada tabela separadamente e combinar resultados

            all_results = []

            

            for table in tables:

                # Buscar em todas as colunas TEXT da tabela

                cursor_info = self._cursor.execute(f"PRAGMA table_info({table})")

                columns = [col[1] for col in cursor_info.fetchall() 

                          if col[1] not in ['id_row', 'parent_id'] and col[2] == 'TEXT']

                

                if not columns:

                    continue

                

                # Construir condições de busca

                conditions = []

                params = []

                for col in columns:

                    if case_sensitive:

                        conditions.append(f'"{col}" LIKE ?')

                    else:

                        conditions.append(f'LOWER("{col}") LIKE LOWER(?)')

                    params.append(f"%{search_term}%")

                

                where_clause = " OR ".join(conditions)

                reg_name = table.replace("REG_", "")

                

                query = f"SELECT '{reg_name}' as registro, * FROM {table} WHERE {where_clause}"

                

                try:

                    df = pd.read_sql_query(query, self._conn, params=params)

                    if not df.empty:

                        all_results.append(df)

                except Exception as e:

                    logger.warning(f"Erro ao buscar em {table}: {e}")

            

            if not all_results:

                return pd.DataFrame()

            

            # Combinar todos os resultados

            final_df = pd.concat(all_results, ignore_index=True)

            

            logger.info(f"Busca por '{search_term}': {len(final_df)} resultados encontrados")

            return final_df

            

        except Exception as e:

            logger.error(f"Erro na busca global: {e}")

            return pd.DataFrame()

    

    def search_invoice(self, invoice_number: str) -> tuple[pd.DataFrame, pd.DataFrame]:

        """

        Busca nota fiscal pelo número, retornando C100 (pai) e C170 (itens) separados.

        

        Args:

            invoice_number: Número da nota fiscal

        

        Returns:

            Tuple com (DataFrame_C100, DataFrame_C170)

        """

        try:

            # Buscar IDs dos C100 pelo número do documento

            cursor = self._cursor.execute(

                "SELECT id_row FROM REG_C100 WHERE NUM_DOC LIKE ?",

                (f"%{invoice_number}%",)

            )

            c100_ids = [row[0] for row in cursor.fetchall()]

            

            if not c100_ids:

                return pd.DataFrame(), pd.DataFrame()

            

            c100_results = []

            c170_results = []

            

            for c100_id in c100_ids:

                # Buscar dados do C100

                c100_df = pd.read_sql_query(

                    "SELECT * FROM REG_C100 WHERE id_row = ?",

                    self._conn,

                    params=[c100_id]

                )

                

                if not c100_df.empty:

                    c100_results.append(c100_df)

                

                # Buscar C170 filhos

                c170_df = pd.read_sql_query(

                    "SELECT * FROM REG_C170 WHERE parent_id = ?",

                    self._conn,

                    params=[c100_id]

                )

                

                if not c170_df.empty:

                    c170_results.append(c170_df)

            

            c100_final = pd.concat(c100_results, ignore_index=True) if c100_results else pd.DataFrame()

            c170_final = pd.concat(c170_results, ignore_index=True) if c170_results else pd.DataFrame()

            

            logger.info(f"Busca nota {invoice_number}: {len(c100_final)} C100 + {len(c170_final)} C170")

            return c100_final, c170_final

            

        except Exception as e:

            logger.error(f"Erro ao buscar nota fiscal: {e}")

            return pd.DataFrame(), pd.DataFrame()

    

    def save_changes(self, reg_type: str, row_id: int, col_name: str, new_value: str, record_history: bool = True) -> bool:

        """

        Salva alterações em uma célula.

        

        Args:

            reg_type: Tipo de registro SPED

            row_id: ID da linha

            col_name: Nome da coluna

            new_value: Novo valor

            record_history: Se True, registra no histórico (para undo/redo)

        """

        try:

            safe_reg = sanitize_reg_type(reg_type)

            # Validar nome da coluna (permitir apenas alfanuméricos e underscore)

            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', col_name):

                logger.error(f"Nome de coluna inválido: {col_name}")

                return False

            

            # Buscar valor antigo para o histórico

            old_value = None

            if record_history:

                try:

                    result = self._cursor.execute(

                        f'SELECT "{col_name}" FROM REG_{safe_reg} WHERE id_row = ?',

                        (row_id,)

                    ).fetchone()

                    old_value = result[0] if result else None

                except sqlite3.Error:

                    pass

            

            self._cursor.execute(

                f'UPDATE REG_{safe_reg} SET "{col_name}" = ? WHERE id_row = ?',

                (new_value, row_id)

            )

            self._conn.commit()

            

            # Registrar no histórico

            if record_history and old_value != new_value:

                op = EditOperation(

                    table=safe_reg,

                    row_id=row_id,

                    column=col_name,

                    old_value=old_value or "",

                    new_value=new_value,

                    description=f"Editar {safe_reg}[{row_id}].{col_name}"

                )

                self.history.push(op)

            

            return True

        except (ValueError, sqlite3.Error) as e:

            logger.error(f"Erro ao salvar: {e}")

            return False

    

    def undo(self) -> bool:

        """

        Desfaz a última operação editada.

        

        Returns:

            True se o undo foi bem-sucedido

        """

        op = self.history.undo()

        if not op:

            return False

        

        try:

            safe_reg = sanitize_reg_type(op.table)

            self._cursor.execute(

                f'UPDATE REG_{safe_reg} SET "{op.column}" = ? WHERE id_row = ?',

                (op.old_value, op.row_id)

            )

            self._conn.commit()

            logger.info(f"Undo: {op}")

            return True

        except (ValueError, sqlite3.Error) as e:

            logger.error(f"Erro ao desfazer: {e}")

            return False

    

    def redo(self) -> bool:

        """

        Refaz a última operação desfeita.

        

        Returns:

            True se o redo foi bem-sucedido

        """

        op = self.history.redo()

        if not op:

            return False

        

        try:

            safe_reg = sanitize_reg_type(op.table)

            self._cursor.execute(

                f'UPDATE REG_{safe_reg} SET "{op.column}" = ? WHERE id_row = ?',

                (op.new_value, op.row_id)

            )

            self._conn.commit()

            logger.info(f"Redo: {op}")

            return True

        except (ValueError, sqlite3.Error) as e:

            logger.error(f"Erro ao refazer: {e}")

            return False

    

    def fix_0200_spaces(self) -> Tuple[int, Optional[str]]:

        """Remove espaços extras das descrições do registro 0200."""

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

        """Recalcula H010 e atualiza H005 baseado em um valor alvo."""

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

        """Executa consulta SQL."""

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

        """Gera string SPED formatada a partir do banco de dados."""

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

        

        all_rows.sort(key=lambda x: (self._block_rank(x[1]), x[0]))

        

        lines: List[str] = []

        buffer_b9: List[str] = []

        types_processed: set = set()

        # 9990 é recalculado ao final do bloco 9

        

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

                # 9990 sera recalculado ao final com a contagem real de linhas do bloco 9
                lines.append("|9990|__QTD_9990__|")

            

            elif reg == '9999':

                # 9999 é processado no final

                pass

            

            elif reg.startswith('9'):

                clean_data = [str(x) if x is not None else "" for x in data]

                buffer_b9.append(f"|{reg}|" + "|".join(clean_data) + "|")

        

        # Adicionar 9999 no final com contagem correta

        total_lines = len(lines) + 1  # +1 para o próprio 9999

        lines.append(f"|9999|{total_lines}|")

        # Recalcular contagens de encerramento de bloco (0990, C990, D990, ..., 9990).
        # Cada encerramento X990 informa a quantidade de linhas do bloco X (incluindo o
        # próprio encerramento). Para o bloco 9 isso inclui o registro 9999.
        block_counts: Dict[str, int] = {}
        for line in lines:
            if line.startswith('|'):
                prefix = line[1]
                block_counts[prefix] = block_counts.get(prefix, 0) + 1

        encerramento_re = re.compile(r'^\|([A-Z0-9])(\d*)(?:990)\|')
        for i, _ in enumerate(lines):
            m = encerramento_re.match(lines[i])
            if m:
                prefix = m.group(1)
                sufixo = m.group(2)
                qtd = block_counts.get(prefix, 0)
                lines[i] = f"|{prefix}{sufixo}990|{qtd}|"

        

        logger.info(f"SPED gerado: {len(lines)} linhas.")

        return "\n".join(lines) + "\n"

    

    def clean_unused_0200(self) -> Tuple[int, int, List[str]]:

        """

        Remove registros 0200 (produtos) que não estão sendo usados em C170 ou H010.

        

        Retorna:

            Tuple[int, int, List[str]]: (total_0200, removidos, lista de itens removidos)

        """

        try:

            # Buscar todos os COD_ITEM do registro 0200

            cursor_0200 = self._cursor.execute(

                'SELECT id_row, "COD_ITEM", "DESCR_ITEM" FROM REG_0200'

            )

            items_0200 = {row[1]: (row[0], row[2]) for row in cursor_0200.fetchall()}

            

            if not items_0200:

                return 0, 0, []

            

            # Buscar COD_ITEM usados em C170 (posição 1 = COD_ITEM)

            items_c170 = set()

            try:

                cursor_c170 = self._cursor.execute(

                    'SELECT DISTINCT "COD_ITEM" FROM REG_C170'

                )

                items_c170 = {row[0] for row in cursor_c170.fetchall()}

            except sqlite3.OperationalError:

                pass  # Tabela não existe

            

            # Buscar COD_ITEM usados em H010 (posição 0 = COD_ITEM)

            items_h010 = set()

            try:

                cursor_h010 = self._cursor.execute(

                    'SELECT DISTINCT "COD_ITEM" FROM REG_H010'

                )

                items_h010 = {row[0] for row in cursor_h010.fetchall()}

            except sqlite3.OperationalError:

                pass  # Tabela não existe

            

            # Buscar COD_ITEM usados em K200 (posição 1 = COD_ITEM)

            items_k200 = set()

            try:

                cursor_k200 = self._cursor.execute(

                    'SELECT DISTINCT "COD_ITEM" FROM REG_K200'

                )

                items_k200 = {row[0] for row in cursor_k200.fetchall()}

            except sqlite3.OperationalError:

                pass  # Tabela não existe

            

            # Itens usados (união de C170, H010 e K200)

            items_usados = items_c170 | items_h010 | items_k200

            

            # Itens não usados

            itens_removidos = []

            ids_para_remover = []

            

            for cod_item, (id_row, descr) in items_0200.items():

                if cod_item not in items_usados:

                    itens_removidos.append(f"{cod_item} - {descr}")

                    ids_para_remover.append(id_row)

            

            # Remover os itens não usados

            if ids_para_remover:

                placeholders = ",".join(["?" for _ in ids_para_remover])

                self._cursor.execute(

                    f'DELETE FROM REG_0200 WHERE id_row IN ({placeholders})',

                    ids_para_remover

                )

                self._conn.commit()

            

            total = len(items_0200)

            removidos = len(itens_removidos)

            

            logger.info(f"Limpeza 0200: {removidos}/{total} itens removidos")

            return total, removidos, itens_removidos

            

        except sqlite3.Error as e:

            logger.error(f"Erro na limpeza 0200: {e}")

            return 0, 0, []





    def import_cte_xml(self, xml_path: str) -> Dict[str, any]:
        """
        Importa dados de um arquivo XML CTE e cria os registros SPED necessarios.
        Adiciona registros ao SPED ja importado (nao destroi dados existentes).

        Args:
            xml_path: Caminho para o arquivo XML da CTE

        Returns:
            Dict com status da operacao e registros afetados
        """
        try:
            from .parser import parse_cte_xml
            cte_data = parse_cte_xml(xml_path)

            cnpj = cte_data.get('cnpj', '')
            ie = cte_data.get('ie', '')
            xnome = cte_data.get('xnome', '')
            rntrc = cte_data.get('rntrc', '')
            chv_cte = cte_data.get('chv_cte', '')
            nct = cte_data.get('nct', '')
            vprest = cte_data.get('vprest', 0.0)
            serie = cte_data.get('serie', '')
            dh_emi = cte_data.get('dh_emi', '')
            cmun_ini = cte_data.get('cmun_ini', '')
            cmun_fim = cte_data.get('cmun_fim', '')
            xlgr = cte_data.get('xlgr', '')
            nro = cte_data.get('nro', '')
            xbairro = cte_data.get('xbairro', '')
            cmun = cte_data.get('cmun', '')
            cep = cte_data.get('cep', '')
            cfop = cte_data.get('cfop', '6932')

            # CFOP de entrada (aquisição de serviço de transporte rodoviário de carga).
            # CT-e de prestação de serviço (6xxx) é espelhado para a entrada correspondente.
            cfop_entrada = CFOP_TRANSPORTE_ENTRADA.get(cfop, '1352')

            # Converte dhemi ISO (2026-07-17T16:12:59-03:00) para DDMMAAAA
            dt_doc = ''
            if dh_emi:
                try:
                    dt_parsed = datetime.fromisoformat(dh_emi)
                    dt_doc = dt_parsed.strftime('%d%m%Y')
                except (ValueError, TypeError):
                    dt_doc = dh_emi[:10].replace('-', '') if len(dh_emi) >= 10 else ''

            if not cnpj:
                raise ValueError("CNPJ da transportadora nao encontrado no XML CTE")

            # --- 1) Garantir tabelas existem (sem destruir dados) ---
            self.ensure_table_structure('0150', 12)
            self.ensure_table_structure('D001', 1)
            self.ensure_table_structure('D100', len(SPED_LAYOUT.get('D100', [])))
            self.ensure_table_structure('D190', len(SPED_LAYOUT.get('D190', [])))

            # Garantir que o cabecalho do bloco D (D001) exista com IND_MOV=0
            # (o bloco D possui dados - fretes do CT-e)
            d001_count = self.get_total_rows('D001')
            if d001_count == 0:
                self._cursor.execute(
                    'INSERT INTO REG_D001 (id_row, parent_id, "IND_MOV") VALUES (?, ?, ?)',
                    (self._get_and_increment_next_id('D001'), 0, '0')
                )
                self._conn.commit()
            else:
                # Atualizar D001 existente: com fretes importados o bloco D possui dados
                primeiro_d001 = self._cursor.execute(
                    'SELECT id_row, "IND_MOV" FROM REG_D001 ORDER BY id_row LIMIT 1'
                ).fetchone()
                if primeiro_d001 and primeiro_d001[1] != '0':
                    self._cursor.execute(
                        'UPDATE REG_D001 SET "IND_MOV" = ? WHERE id_row = ?',
                        ('0', primeiro_d001[0])
                    )
                    self._conn.commit()

            # --- 2) Verificar se transportadora ja existe em 0150 ---
            cod_part = None
            new_0150_id = None
            transportadora_reutilizada = False
            existing_0150 = self.get_data('0150')
            if not existing_0150.empty:
                cnpj_matches = existing_0150[existing_0150.get('CNPJ', '') == cnpj]
                if not cnpj_matches.empty:
                    row = cnpj_matches.iloc[0]
                    cod_part = str(row.get('COD_PART', ''))
                    new_0150_id = int(row.get('id_row', 0))
                    transportadora_reutilizada = True

            # --- 3) Inserir novo registro 0150 (transportadora) se ainda nao existir ---
            if cod_part is None:
                new_0150_id = self._get_and_increment_next_id('0150')
                max_existing = self._cursor.execute('SELECT MAX(id_row) FROM REG_0150').fetchone()[0]
                if max_existing and max_existing >= new_0150_id:
                    new_0150_id = max_existing + 1
                self._next_ids['0150'] = new_0150_id + 1

                # Gerar COD_PART automatico (T + CNPJ ou sequencial)
                cod_part = f"T{cnpj[:8]}"
                self._cursor.execute(
                    'INSERT INTO REG_0150 (id_row, parent_id, "COD_PART", "NOME", "COD_PAIS", "CNPJ", "CPF", "IE", "COD_MUN", "SUFRAMA", "END", "NUM", "COMPL", "BAIRRO") '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (new_0150_id, 0, cod_part, xnome, '1058', cnpj, '', ie, cmun, '', xlgr, nro, '', xbairro)
                )
                self._conn.commit()

            # --- 4) Inserir registro D100 ---
            new_d100_id = self._cursor.execute('SELECT COALESCE(MAX(id_row), 0) + 1 FROM REG_D100').fetchone()[0]
            dados_d100 = [
                0,      # IND_OPER (0=entrada, 1=saida)
                1,      # IND_EMIT (1=emit propria)
                cod_part,  # COD_PART referencia 0150
                '57',   # COD_MOD (57 = CT-e)
                '00',   # COD_SIT
                serie,  # SER
                '',     # SUB
                nct,  # NUM_DOC
                chv_cte,  # CHV_CTE
                dt_doc,  # DT_DOC
                dt_doc,  # DT_A_P
                '0',    # TP_CT_E
                '',     # CHV_CTE_REF
                str(vprest).replace('.', ','),  # VL_DOC
                '',     # VL_DESC
                '0',    # IND_FRT
                str(vprest).replace('.', ','),  # VL_SERV
                '0',    # VL_BC_ICMS
                '',     # VL_ICMS
                str(vprest).replace('.', ','),  # VL_NT
                '',     # COD_INF
                '',     # COD_CTA
                cmun_ini,  # COD_MUN_ORIG
                cmun_fim,  # COD_MUN_DEST
            ]
            colunas_d100 = '(id_row, parent_id, "IND_OPER", "IND_EMIT", "COD_PART", "COD_MOD", "COD_SIT", "SER", "SUB", "NUM_DOC", "CHV_CTE", "DT_DOC", "DT_A_P", "TP_CT_E", "CHV_CTE_REF", "VL_DOC", "VL_DESC", "IND_FRT", "VL_SERV", "VL_BC_ICMS", "VL_ICMS", "VL_NT", "COD_INF", "COD_CTA", "COD_MUN_ORIG", "COD_MUN_DEST")'
            placeholders_d100 = ','.join(['?'] * 26)
            sql_d100 = f'INSERT INTO REG_D100 {colunas_d100} VALUES ({placeholders_d100})'
            self._cursor.execute(sql_d100, [new_d100_id, 0] + dados_d100)
            self._conn.commit()

            # --- 5) Inserir registro D190 (filho do D100) ---
            new_d190_id = self._cursor.execute('SELECT COALESCE(MAX(id_row), 0) + 1 FROM REG_D190').fetchone()[0]
            self._cursor.execute(
                'INSERT INTO REG_D190 (id_row, parent_id, "CST_ICMS", "CFOP", "ALIQ_ICMS", "VL_OPR", "VL_BC_ICMS", "VL_ICMS", "VL_RED_BC", "COD_OBS") '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (new_d190_id, new_d100_id, '090', cfop_entrada, '0',
                 str(vprest).replace('.', ','), '0', '0', '0', '')
            )
            self._conn.commit()

            # --- 6) Contar registros do bloco D para atualizar D990 ---
            d100_count = self.get_total_rows('D100')
            d190_count = self.get_total_rows('D190')
            d001_count = self.get_total_rows('D001')
            d990_total = d001_count + d100_count + d190_count + 1  # +1 para o proprio D990

            # Criar/atualizar REG_D990
            d990_exists = self._cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='REG_D990'"
            ).fetchone()
            if not d990_exists:
                self._cursor.execute(
                    'CREATE TABLE REG_D990 (id_row INTEGER PRIMARY KEY, parent_id INTEGER, "field_1" TEXT)'
                )
                self._cursor.execute(
                    'INSERT INTO REG_D990 (id_row, parent_id, "field_1") VALUES (1, 0, ?)',
                    (str(d990_total),)
                )
            else:
                # Atualizar contagem existente
                row = self._cursor.execute('SELECT id_row FROM REG_D990 ORDER BY id_row LIMIT 1').fetchone()
                if row:
                    self._cursor.execute(
                        'UPDATE REG_D990 SET "field_1" = ? WHERE id_row = ?',
                        (str(d990_total), row[0])
                    )
            self._conn.commit()

            # Criar/atualizar REG_9900 (referencias para D100, D190, D990)
            reg_9900_exists = self._cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='REG_9900'"
            ).fetchone()
            if not reg_9900_exists:
                self._cursor.execute(
                    'CREATE TABLE REG_9900 (id_row INTEGER PRIMARY KEY, parent_id INTEGER, "field_1" TEXT, "field_2" TEXT)'
                )
                self._cursor.executemany(
                    'INSERT INTO REG_9900 (id_row, parent_id, "field_1", "field_2") VALUES (?, ?, ?, ?)',
                    [(1, 0, 'D100', str(d100_count)),
                     (2, 0, 'D190', str(d190_count)),
                     (3, 0, 'D990', '1')]
                )
            else:
                # Verificar se ja existe referencia para D100, se nao, inserir
                for reg_code, count in [('D100', d100_count), ('D190', d190_count), ('D990', '1')]:
                    existing = self._cursor.execute(
                        'SELECT id_row FROM REG_9900 WHERE "field_1" = ?', (reg_code,)
                    ).fetchone()
                    if existing:
                        self._cursor.execute(
                            'UPDATE REG_9900 SET "field_2" = ? WHERE id_row = ?',
                            (str(count), existing[0])
                        )
                    else:
                        new_id = self._cursor.execute(
                            'SELECT COALESCE(MAX(id_row), 0) + 1 FROM REG_9900'
                        ).fetchone()[0]
                        self._cursor.execute(
                            'INSERT INTO REG_9900 (id_row, parent_id, "field_1", "field_2") VALUES (?, ?, ?, ?)',
                            (new_id, 0, reg_code, str(count))
                        )
            self._conn.commit()

            # Atualizar REG_B990 se existir
            b990_exists = self._cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='REG_B990'"
            ).fetchone()
            if b990_exists:
                cols_info = self._cursor.execute('PRAGMA table_info(REG_B990)').fetchall()
                col_names = [c[1] for c in cols_info]
                data_col = col_names[2] if len(col_names) > 2 else 'field_1'
                self._cursor.execute(
                    f'UPDATE REG_B990 SET "{data_col}" = ? WHERE id_row = 1',
                    (str(d990_total),)
                )
                self._conn.commit()

            if transportadora_reutilizada:
                transportadora_msg = f"Transportadora ja cadastrada, COD_PART {cod_part} reutilizado (0150 id={new_0150_id})."
            else:
                transportadora_msg = f"Transportadora criada: {xnome} (CNPJ: {cnpj}, COD_PART: {cod_part})"

            return {
                'status': 'success',
                'message': f"CTE importado com sucesso!\n"
                           f"{transportadora_msg}\n"
                           f"RNTRC: {rntrc}\n"
                           f"Chave CT-e: {chv_cte}\n"
                           f"NCT: {nct}\n"
                           f"Valor Servico: R$ {vprest:.2f}\n"
                           f"Registros criados: D100(id={new_d100_id}), D190(id={new_d190_id})\n"
                           f"D990 atualizado: {d990_total} linhas no bloco D",
                '0150_row_id': new_0150_id,
                'D100_row_id': new_d100_id,
                'D190_row_id': new_d190_id,
                'D100_count': d100_count,
                'cod_part': cod_part,
                'cnpj': cnpj,
                'ie': ie,
                'vprest': vprest
            }

        except ET.ParseError as e:
            logger.error(f"Erro ao fazer parse do XML CTE: {e}")
            return {'status': 'error', 'message': f"Erro ao parsear XML: {str(e)}"}
        except FileNotFoundError as e:
            logger.error(f"Arquivo XML nao encontrado: {e}")
            return {'status': 'error', 'message': f"Arquivo nao encontrado: {str(e)}"}
        except Exception as e:
            logger.error(f"Erro inesperado importando CTE: {e}")
            return {'status': 'error', 'message': f"Erro inesperado: {str(e)}"}

