-- 用户资料表
CREATE TABLE `user_profile` (
  `id` bigint NOT NULL COMMENT '主键',
  `name` varchar(50) COMMENT '显示名称'
) COMMENT='用户资料';

INSERT INTO `user_profile` (`id`, `name`) VALUES
  (1, 'A'),
  (2, 'B');

