-- ============================================================
-- Estudio Postural - Esquema PostgreSQL (Supabase)
-- Idempotente: puede ejecutarse más de una vez sin errores.
-- Ejecutar con: python scripts/init_db.py
-- ============================================================

-- ------------------------------------------------------------
-- Utilidades
-- ------------------------------------------------------------

-- Trigger que actualiza updated_at automáticamente
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ------------------------------------------------------------
-- USUARIOS (administradores y recepción)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id              BIGSERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    apellido        VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    rol             VARCHAR(20) NOT NULL DEFAULT 'RECEPCION'
                    CHECK (rol IN ('ADMIN', 'RECEPCION')),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_usuarios_email UNIQUE (email)
);

DROP TRIGGER IF EXISTS trg_usuarios_updated ON usuarios;
CREATE TRIGGER trg_usuarios_updated
    BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- ALUMNOS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alumnos (
    id                  BIGSERIAL PRIMARY KEY,
    nombre              VARCHAR(100) NOT NULL,
    apellido            VARCHAR(100) NOT NULL,
    dni                 VARCHAR(20),
    fecha_nacimiento    DATE,
    telefono            VARCHAR(40),
    email               VARCHAR(255),
    direccion           VARCHAR(255),
    contacto_emergencia VARCHAR(150),
    telefono_emergencia VARCHAR(40),
    observaciones       TEXT,                -- información privada (salud/movimiento)
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_alta          DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_alumnos_dni UNIQUE (dni),
    CONSTRAINT ck_alumnos_email CHECK (
        email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    )
);

DROP TRIGGER IF EXISTS trg_alumnos_updated ON alumnos;
CREATE TRIGGER trg_alumnos_updated
    BEFORE UPDATE ON alumnos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_alumnos_apellido ON alumnos (apellido);
CREATE INDEX IF NOT EXISTS idx_alumnos_activo ON alumnos (activo);

-- ------------------------------------------------------------
-- ACTIVIDADES (Terapia Postural, Pilates, Yoga...)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS actividades (
    id                BIGSERIAL PRIMARY KEY,
    nombre            VARCHAR(120) NOT NULL,
    descripcion       TEXT,
    duracion_minutos  INTEGER NOT NULL DEFAULT 60
                      CHECK (duracion_minutos > 0 AND duracion_minutos <= 240),
    precio            NUMERIC(12,2) NOT NULL DEFAULT 0
                      CHECK (precio >= 0),
    activo            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_actividades_nombre UNIQUE (nombre)
);

DROP TRIGGER IF EXISTS trg_actividades_updated ON actividades;
CREATE TRIGGER trg_actividades_updated
    BEFORE UPDATE ON actividades
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- PROFESORES / INSTRUCTORES
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profesores (
    id            BIGSERIAL PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL,
    apellido      VARCHAR(100) NOT NULL,
    telefono      VARCHAR(40),
    email         VARCHAR(255),
    especialidad  VARCHAR(150),
    activo        BOOLEAN NOT NULL DEFAULT TRUE,
    observaciones TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_profesores_email CHECK (
        email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    )
);

DROP TRIGGER IF EXISTS trg_profesores_updated ON profesores;
CREATE TRIGGER trg_profesores_updated
    BEFORE UPDATE ON profesores
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- HORARIOS (grilla semanal repetitiva)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS horarios (
    id            BIGSERIAL PRIMARY KEY,
    actividad_id  BIGINT NOT NULL REFERENCES actividades (id) ON DELETE RESTRICT,
    profesor_id   BIGINT NOT NULL REFERENCES profesores (id) ON DELETE RESTRICT,
    dia_semana    SMALLINT NOT NULL CHECK (dia_semana BETWEEN 1 AND 7), -- 1=Lunes ... 7=Domingo
    hora_inicio   TIME NOT NULL,
    hora_fin      TIME NOT NULL,
    cupo_maximo   INTEGER NOT NULL DEFAULT 8 CHECK (cupo_maximo > 0),
    sala          VARCHAR(60),
    activo        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_horarios_horas CHECK (hora_fin > hora_inicio),
    -- Mismo horario no puede pisarse en la misma sala
    CONSTRAINT uq_horarios_dia_hora_sala UNIQUE (dia_semana, hora_inicio, sala)
);

DROP TRIGGER IF EXISTS trg_horarios_updated ON horarios;
CREATE TRIGGER trg_horarios_updated
    BEFORE UPDATE ON horarios
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_horarios_dia ON horarios (dia_semana, activo);
CREATE INDEX IF NOT EXISTS idx_horarios_profesor ON horarios (profesor_id);
CREATE INDEX IF NOT EXISTS idx_horarios_actividad ON horarios (actividad_id);

-- ------------------------------------------------------------
-- TURNOS (instancia concreta de un horario en una fecha)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turnos (
    id            BIGSERIAL PRIMARY KEY,
    horario_id    BIGINT NOT NULL REFERENCES horarios (id) ON DELETE CASCADE,
    fecha         DATE NOT NULL,
    hora_inicio   TIME NOT NULL,
    hora_fin      TIME NOT NULL,
    estado        VARCHAR(20) NOT NULL DEFAULT 'programado'
                  CHECK (estado IN ('programado', 'confirmado', 'cancelado', 'completado')),
    observaciones TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_turnos_horas CHECK (hora_fin > hora_inicio),
    -- Un horario no puede tener dos turnos en la misma fecha
    CONSTRAINT uq_turnos_horario_fecha UNIQUE (horario_id, fecha)
);

DROP TRIGGER IF EXISTS trg_turnos_updated ON turnos;
CREATE TRIGGER trg_turnos_updated
    BEFORE UPDATE ON turnos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_turnos_fecha ON turnos (fecha);
CREATE INDEX IF NOT EXISTS idx_turnos_estado ON turnos (estado);

-- ------------------------------------------------------------
-- INSCRIPCIONES (alumno <-> horario)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inscripciones (
    id            BIGSERIAL PRIMARY KEY,
    alumno_id     BIGINT NOT NULL REFERENCES alumnos (id) ON DELETE CASCADE,
    horario_id    BIGINT NOT NULL REFERENCES horarios (id) ON DELETE CASCADE,
    fecha_inicio  DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin     DATE,
    estado        VARCHAR(20) NOT NULL DEFAULT 'activa'
                  CHECK (estado IN ('activa', 'finalizada', 'cancelada')),
    observaciones TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_inscripciones_updated ON inscripciones;
CREATE TRIGGER trg_inscripciones_updated
    BEFORE UPDATE ON inscripciones
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Un alumno no puede estar dos veces activo en el mismo horario
CREATE UNIQUE INDEX IF NOT EXISTS uq_inscripcion_activa
    ON inscripciones (alumno_id, horario_id)
    WHERE estado = 'activa';

CREATE INDEX IF NOT EXISTS idx_inscripciones_alumno ON inscripciones (alumno_id);
CREATE INDEX IF NOT EXISTS idx_inscripciones_horario ON inscripciones (horario_id);

-- ------------------------------------------------------------
-- ASISTENCIAS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistencias (
    id            BIGSERIAL PRIMARY KEY,
    turno_id      BIGINT NOT NULL REFERENCES turnos (id) ON DELETE CASCADE,
    alumno_id     BIGINT NOT NULL REFERENCES alumnos (id) ON DELETE CASCADE,
    estado        VARCHAR(20) NOT NULL DEFAULT 'presente'
                  CHECK (estado IN ('presente', 'ausente', 'justificado')),
    observaciones TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_asistencia_turno_alumno UNIQUE (turno_id, alumno_id)
);

DROP TRIGGER IF EXISTS trg_asistencias_updated ON asistencias;
CREATE TRIGGER trg_asistencias_updated
    BEFORE UPDATE ON asistencias
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_asistencias_alumno ON asistencias (alumno_id);
CREATE INDEX IF NOT EXISTS idx_asistencias_estado ON asistencias (estado);

-- ------------------------------------------------------------
-- MÉTODOS DE PAGO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metodos_pago (
    id         BIGSERIAL PRIMARY KEY,
    nombre     VARCHAR(80) NOT NULL,
    activo     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_metodos_pago_nombre UNIQUE (nombre)
);

-- ------------------------------------------------------------
-- PAGOS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pagos (
    id                BIGSERIAL PRIMARY KEY,
    alumno_id         BIGINT NOT NULL REFERENCES alumnos (id) ON DELETE CASCADE,
    concepto          VARCHAR(200) NOT NULL,
    monto             NUMERIC(12,2) NOT NULL CHECK (monto >= 0),
    fecha_pago        DATE,
    fecha_vencimiento DATE,
    metodo_pago_id    BIGINT REFERENCES metodos_pago (id) ON DELETE SET NULL,
    estado            VARCHAR(20) NOT NULL DEFAULT 'pendiente'
                      CHECK (estado IN ('pagado', 'pendiente', 'vencido', 'cancelado')),
    observaciones     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Un pago pagado siempre tiene fecha de pago
    CONSTRAINT ck_pagos_fecha CHECK (
        estado <> 'pagado' OR fecha_pago IS NOT NULL
    )
);

DROP TRIGGER IF EXISTS trg_pagos_updated ON pagos;
CREATE TRIGGER trg_pagos_updated
    BEFORE UPDATE ON pagos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_pagos_alumno ON pagos (alumno_id);
CREATE INDEX IF NOT EXISTS idx_pagos_estado ON pagos (estado);
CREATE INDEX IF NOT EXISTS idx_pagos_vencimiento ON pagos (fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_fecha_pago ON pagos (fecha_pago);

-- ------------------------------------------------------------
-- CONFIGURACIÓN (clave/valor del estudio)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS configuracion (
    clave       VARCHAR(80) PRIMARY KEY,
    valor       TEXT,
    descripcion VARCHAR(255),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- Auditoría
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auditoria (
    id          BIGSERIAL PRIMARY KEY,
    usuario_id  BIGINT REFERENCES usuarios (id) ON DELETE SET NULL,
    accion      VARCHAR(60) NOT NULL,   -- crear / modificar / eliminar / login ...
    entidad     VARCHAR(60) NOT NULL,   -- alumno / pago / turno ...
    entidad_id  BIGINT,
    descripcion TEXT,
    fecha       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_entidad ON auditoria (entidad, entidad_id);

-- ------------------------------------------------------------
-- Migraciones (idempotentes para bases ya creadas)
-- ------------------------------------------------------------

-- Primer ingreso: forzar cambio de contraseña
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE;
