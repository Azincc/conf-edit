-- ConfEdit MySQL 示例：部门表
CREATE TABLE `demo_department` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '部门主键',
  `department_code` VARCHAR(32) NOT NULL COMMENT '部门编码',
  `department_name` VARCHAR(100) NOT NULL COMMENT '部门名称',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用：1 是，0 否',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`,`department_code`,`department_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='示例部门表';
INSERT INTO `demo_department`
  (`id`, `department_code`, `department_name`, `enabled`, `created_at`)
VALUES
  (1, 'RD', '研发部', 1, '2026-01-01 09:00:00'),
  (2, 'OPS', '运维部', 1, '2026-01-01 09:00:00');

-- ConfEdit MySQL 示例：用户表
CREATE TABLE `demo_user` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户主键',
  `username` VARCHAR(64) NOT NULL COMMENT '登录名',
  `display_name` VARCHAR(100) NOT NULL COMMENT '显示名称',
  `department_id` BIGINT UNSIGNED NOT NULL COMMENT '所属部门主键',
  `status` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '状态：1 启用，0 停用',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_demo_user_username` (`username`),
  KEY `idx_demo_user_department` (`department_id`),
  CONSTRAINT `fk_demo_user_department`
    FOREIGN KEY (`department_id`) REFERENCES `demo_department` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='示例用户表';

INSERT INTO `demo_user`
  (`id`, `username`, `display_name`, `department_id`, `status`, `created_at`)
VALUES
  (1, 'zhangsan', '张三', 1, 1, '2026-01-01 09:10:00'),
  (2, 'lisi', '李四', 2, 1, '2026-01-01 09:20:00');
