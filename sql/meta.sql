SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS table_info (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL,
    description TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='元数据表信息表';

CREATE TABLE IF NOT EXISTS column_info (
    id VARCHAR(128) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    type VARCHAR(64),
    role VARCHAR(32),
    examples JSON,
    description TEXT,
    alias JSON,
    table_id VARCHAR(64) NOT NULL,
    INDEX idx_column_info_table_id (table_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='元数据字段信息表';

CREATE TABLE IF NOT EXISTS metric_info (
    id VARCHAR(128) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    relevant_columns JSON,
    alias JSON
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='指标信息表';

CREATE TABLE IF NOT EXISTS column_metric (
    column_id VARCHAR(128) NOT NULL,
    metric_id VARCHAR(128) NOT NULL,
    PRIMARY KEY (column_id, metric_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='字段指标关联表';
