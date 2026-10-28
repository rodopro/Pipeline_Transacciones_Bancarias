"""Esquemas estrictos Pydantic v2; validación de estructura y reglas de negocio."""
from __future__ import annotations

from datetime import date
from math import isclose
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


class TransaccionLimpia(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)

    transaccion_id: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=100)
    tipo_origen: Literal["ATM", "SPEI_DIGITAL"]
    fecha_corta: str
    moneda: Literal["MXN", "USD"]
    monto_original: float = Field(ge=0)
    monto_mxn: float = Field(ge=0)
    monto_mxn_capped: float = Field(ge=0)
    monto_minmax: float = Field(ge=0, le=1)
    nivel_monto: Literal["Bajo", "Medio", "Alto"]
    notification_email: str
    beneficiary_clabe: str | None
    tipo_operacion: str | None
    comision_aplicada: float | None
    es_huerfano: bool
    obs_calidad: str = ""
    datos_origen_json: str = "{}"

    @field_validator("transaccion_id", "account_id")
    @classmethod
    def identificador_valido(cls, valor: str, info: ValidationInfo) -> str:
        if not valor.strip() or valor != valor.strip():
            raise ValueError("Identificador vacío o con espacios externos")
        contexto = info.context or {}
        if info.field_name == "account_id" and valor not in contexto.get("cuentas_validas", set()):
            raise ValueError("Cuenta huérfana no registrada en Core Bancario")
        if info.field_name == "transaccion_id" and valor in contexto.get("ids_vistos", set()):
            raise ValueError("Identificador de transacción duplicado en el lote")
        return valor

    @field_validator("fecha_corta")
    @classmethod
    def fecha_iso(cls, valor: str) -> str:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
            raise ValueError("Fecha requerida en formato YYYY-MM-DD")
        date.fromisoformat(valor)  # Rechaza días y meses imposibles.
        return valor

    @field_validator("notification_email")
    @classmethod
    def correo_valido(cls, valor: str) -> str:
        if valor != "ANONIMO" and not EMAIL.fullmatch(valor):
            raise ValueError("Correo de notificación inválido; se permite ANONIMO")
        return valor

    @field_validator("beneficiary_clabe")
    @classmethod
    def clabe_valida(cls, valor: str | None) -> str | None:
        if valor is not None and not re.fullmatch(r"[0-9]{18}", valor):
            raise ValueError("La CLABE debe contener exactamente 18 dígitos ASCII")
        return valor

    @field_validator("es_huerfano")
    @classmethod
    def sin_huerfanos(cls, valor: bool) -> bool:
        if valor:
            raise ValueError("Cuenta marcada como huérfana en la integración")
        return valor

    @field_validator("monto_original", "monto_mxn", "monto_mxn_capped", "monto_minmax", "comision_aplicada", mode="before")
    @classmethod
    def sin_booleanos_numericos(cls, valor):
        if isinstance(valor, bool):
            raise ValueError("Un booleano no es un importe numérico")
        return valor

    @field_validator("obs_calidad")
    @classmethod
    def sin_corrupcion_previa(cls, valor: str) -> str:
        if "NO_NUMERICO" in valor.upper():
            raise ValueError(f"Corrupción detectada en una fase previa: {valor}")
        return valor

    @model_validator(mode="after")
    def coherencia_negocio(self):
        if self.tipo_origen == "ATM":
            if self.moneda != "MXN":
                raise ValueError("Las operaciones ATM deben estar en MXN")
            if self.tipo_operacion not in {"RETIRO", "DEPOSITO", "PAGO_SERVICIOS", "CONSULTA_SALDO"}:
                raise ValueError("Tipo de operación ATM ausente o desconocido")
            if self.comision_aplicada is None or self.comision_aplicada < 0:
                raise ValueError("La comisión ATM debe ser numérica y no negativa")
        elif self.beneficiary_clabe is None:
            raise ValueError("Las transferencias digitales requieren CLABE")
        consulta = self.tipo_origen == "ATM" and self.tipo_operacion == "CONSULTA_SALDO"
        if consulta:
            if any(x != 0 for x in (self.monto_original, self.monto_mxn, self.monto_mxn_capped)):
                raise ValueError("CONSULTA_SALDO debe tener importe cero")
        elif min(self.monto_original, self.monto_mxn, self.monto_mxn_capped) <= 0:
            raise ValueError("Las operaciones monetarias requieren importes positivos")
        esperado = self.monto_original * (19.50 if self.moneda == "USD" else 1.0)
        if not isclose(self.monto_mxn, esperado, rel_tol=1e-9, abs_tol=0.01):
            raise ValueError("Conversión a MXN inconsistente con la paridad 19.50")
        if self.monto_mxn_capped > self.monto_mxn + 0.01:
            raise ValueError("El capping no debe aumentar el importe")
        return self


class RegistroCuarentena(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    numero_fila: int = Field(ge=1)
    transaccion_id: str | None
    tipo_origen: str | None
    motivo_rechazo_cuarentena: str = Field(min_length=1)
    errores_validacion_json: str = Field(min_length=2)
    registro_original_json: str = Field(min_length=2)
