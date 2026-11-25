# ITAM-X — IT设备与耗材全生命周期管理系统

一码贯穿全生命周期：资产数字档案 + 扫码业务 + 状态机 + 耗材批次/库存流水 + 维修系统 API + 全链路审计。

技术栈：Python 3 / Flask / SQLite(WAL) / 原生 JS 单页前端。模块化单体，API-first（`/api/v1`）。

## 快速开始

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q          # 16 项测试
python run.py                      # http://localhost:8080
```

首次启动自动建库并创建 `admin` 账号，密码为环境变量 `ITAMX_ADMIN_PASSWORD`，未设置则随机生成并写入 `data/admin_password.txt`（权限 600）。

## 部署到 192.168.2.3

```bash
./deploy/deploy.sh                 # 默认 debian@192.168.2.3:/home/debian/ITAM-X，需免密 SSH
# 服务器上管理：./deploy/itamx.sh start|stop|restart|status|logs
```

服务器需 `python3-venv`。配置在服务器的 `.env`（首次部署自动生成，含随机 Webhook 密钥）：

| 变量 | 说明 |
|---|---|
| `ITAMX_PORT` | 端口，默认 8080 |
| `ITAMX_WEBHOOK_SECRET` | 维修系统 Webhook 的 HMAC-SHA256 密钥；未设置时 Webhook 拒绝服务 |
| `ITAMX_REPAIR_URL` / `ITAMX_REPAIR_TOKEN` | 维修系统地址/令牌；不设置则为本地模式（工单仅存本系统） |
| `ITAMX_ADMIN_PASSWORD` | 首次初始化的 admin 密码 |

SQLite 要求 **单 worker 进程**（脚本已按 `-w 1 --threads 8` 配置）。

## 核心设计

- **状态只能由业务动作改变**：`POST /assets/{id}/actions/{action}`，`PATCH` 禁止改状态/持有人。
  `purchase → receive → inspect → stock_in → issue → (transfer / loan / return / repair_request) → repair_complete → … → retire_request → scrap(双人审批) → dispose`
- **一事一流水**：每个动作写 `asset_events`（事件号、操作人、终端、扫码方式、Trace ID）。
- **审计不可篡改**：`audit_logs` 哈希链 + 数据库触发器禁止 UPDATE/DELETE（`asset_events`、`inventory_transactions` 同样）；`GET /audit/verify` 校验链完整性。
- **库存以流水为准**：`inventory_transactions` 只增不改，余额 = 流水求和；按批次先到期先出（FEFO），锁定/过期批次不可发放，禁止负库存；盘点只能写调整流水。批次追溯：`GET /inventory/batches/trace`。
- **序列号级耗材**（SSD/内存等）：`serial_tracked`，可 `POST /components/install` 装入/拆下设备，记入设备时间线。
- **二维码**只放 UUID：`ITAM://ASSET/{uuid}`；`POST /scan/resolve` 统一解析资产/耗材/位置/仓库/员工码，也接受资产编号、SN、工号。
- **维修集成**：
  - 出站：申请维修 → 本地先落工单并置 `REPAIR`，再 `POST {REPAIR_URL}/api/v1/repairs`（带 `Idempotency-Key`、`X-Signature`、`X-Trace-Id`）。失败只标记 `FAILED`，不影响业务状态；`POST /integrations/repair/retry` 补偿重试。
  - 入站：`POST /api/v1/webhooks/repair-events`，校验 `X-Signature: sha256=HMAC(body)`，按 `eventId` 幂等，重复事件和已关闭工单不会重复处理；事件 `REPAIR_STARTED / REPAIR_COMPLETED / REPAIR_CANCELLED`。完成后资产 → `READY_FOR_USE`，费用/结果挂入档案。
  - 全部调用记录在 `integration_logs`。
- **角色**：SUPER_ADMIN、IT_ADMIN、IT_OPERATOR、WAREHOUSE_ADMIN、DEPARTMENT_MANAGER、EMPLOYEE（仅见/操作自己持有的资产）、AUDITOR（只读）、REPAIR_OPERATOR。
- **异常/通知**：借用超期、维修超 48h、维修未同步、保修 30 天内到期、长期闲置、低库存、批次过期、盘点异常（`/anomalies`，`/notifications/publish` 幂等落库）。
- **报表**：总览、部门/类别分布、维修 TOP/平均时长、单台 TCO 与健康度。

## 与规格书的差异（v1 取舍）

已实现 G0–G6、G8 的核心和 G9 的自动化验证。**未实现**：
PostgreSQL / Redis / 对象存储（用 SQLite，附件仅支持签名/照片字段存文本，无独立附件表）；
OA / 企业微信 / 钉钉 / 邮件审批与通知推送（只落库通知）；原生 Android/PDA App（提供响应式网页 + BarcodeDetector 摄像头扫码，扫码枪可直接用）；
采购单/到货单实体（资产经 `purchase→receive→inspect→stock_in` 动作建立履历）；标签打印；资产关系图（仅父子字段与部件安装）；
状态机中省略 `ASSIGNED`/`RETURNED` 中间态（领用直接 `IN_USE`，归还直接回 `IN_STOCK`，事件里保留完整记录）。

## 安全提示

登录有简单失败锁定（内存级，单进程）；令牌 12 小时过期，库中仅存哈希。建议放在内网或反向代理 HTTPS 之后；首次登录后请修改/新建管理员账号。
