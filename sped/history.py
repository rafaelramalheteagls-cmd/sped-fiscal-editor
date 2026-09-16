"""
Módulo de histórico de edições (Undo/Redo).
Implementa sistema de undo/redo para operações no SPED.
"""

from typing import Optional, Any, Callable
from dataclasses import dataclass, field
from collections import deque


@dataclass
class EditOperation:
    """Representa uma operação de edição"""
    table: str
    row_id: int
    column: str
    old_value: Any
    new_value: Any
    description: str = ""
    
    def __str__(self) -> str:
        return f"{self.table}[{self.row_id}].{self.column}: '{self.old_value}' -> '{self.new_value}'"


class EditHistory:
    """
    Gerencia histórico de edições com suporte a Undo/Redo.
    
    Exemplo:
        history = EditHistory(max_size=100)
        history.push(EditOperation("C100", 1, "VL_DOC", "1000", "1500"))
        history.undo()  # Reverte para "1000"
        history.redo()  # Aplica "1500" novamente
    """
    
    def __init__(self, max_size: int = 100):
        """
        Inicializa o histórico.
        
        Args:
            max_size: Número máximo de operações armazenadas
        """
        self.max_size = max_size
        self._undo_stack: deque = deque(maxlen=max_size)
        self._redo_stack: deque = deque(maxlen=max_size)
        self._listeners: list = []
    
    def push(self, operation: EditOperation) -> None:
        """
        Adiciona uma operação ao histórico.
        
        Args:
            operation: Operação de edição realizada
        """
        self._undo_stack.append(operation)
        self._redo_stack.clear()  # Limpa redo ao fazer nova edição
        self._notify_listeners()
    
    def undo(self) -> Optional[EditOperation]:
        """
        Desfaz a última operação.
        
        Returns:
            A operação desfeita, ou None se não houver nada para desfazer
        """
        if not self._undo_stack:
            return None
        operation = self._undo_stack.pop()
        self._redo_stack.append(operation)
        self._notify_listeners()
        return operation
    
    def redo(self) -> Optional[EditOperation]:
        """
        Refaz a última operação desfeita.
        
        Returns:
            A operação refeita, ou None se não houver nada para refazer
        """
        if not self._redo_stack:
            return None
        operation = self._redo_stack.pop()
        self._undo_stack.append(operation)
        self._notify_listeners()
        return operation
    
    def can_undo(self) -> bool:
        """Verifica se há operações para desfazer."""
        return len(self._undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Verifica se há operações para refazer."""
        return len(self._redo_stack) > 0
    
    def clear(self) -> None:
        """Limpa todo o histórico."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_listeners()
    
    def get_undo_description(self) -> Optional[str]:
        """Retorna descrição da próxima operação de undo."""
        if not self._undo_stack:
            return None
        return str(self._undo_stack[-1])
    
    def get_redo_description(self) -> Optional[str]:
        """Retorna descrição da próxima operação de redo."""
        if not self._redo_stack:
            return None
        return str(self._redo_stack[-1])
    
    @property
    def undo_count(self) -> int:
        """Número de operações disponíveis para undo."""
        return len(self._undo_stack)
    
    @property
    def redo_count(self) -> int:
        """Número de operações disponíveis para redo."""
        return len(self._redo_stack)
    
    def add_listener(self, callback: Callable) -> None:
        """Adiciona callback para notificações de mudança."""
        self._listeners.append(callback)
    
    def _notify_listeners(self) -> None:
        """Notifica listeners sobre mudança no histórico."""
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass  # Ignora erros nos listeners
