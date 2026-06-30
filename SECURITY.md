# 安全策略 (Security Policy)

## 支持的版本 (Supported Versions)

| 版本 (Version) | 支持状态 (Supported) |
|---------------|---------------------|
| v5.x (latest)  | ✅ 完全支持 (Active) |
| v4.x          | ⚠️ 有限支持 (Security fixes only) |
| v3.x 及更早    | ❌ 不再支持 (End of life) |

## 报告漏洞 (Reporting a Vulnerability)

我们非常重视安全问题。如果发现安全漏洞，**请勿在 GitHub Issues 中公开披露**。

请按照以下步骤操作：

1. **发送邮件至：** [your-email@example.com]
2. **邮件主题：** `[VidDub Security] 漏洞描述`
3. **邮件内容应包括：**
   - 漏洞类型（如 XSS、SQL 注入、RCE 等）
   - 影响范围
   - 复现步骤（包含 PoC 最佳）
   - 可能的修复建议

我们承诺：
- **48 小时内**确认收到报告
- **7 天内**给出初步评估
- **14 天内**（取决于复杂度）发布修复版本

## 安全最佳实践 (Security Best Practices)

### 部署安全

- 请勿将 `backend/.env` 提交到版本控制系统
- 使用强随机密钥（建议 32 位以上字符）
- 在生产环境中使用 HTTPS
- 定期轮换 API 密钥

### API 密钥安全

- 不要在代码中硬编码 API 密钥
- 使用环境变量管理所有敏感配置
- 限制 API 密钥的权限范围
- 定期检查密钥使用情况

### 依赖安全

- 定期运行 `pip audit` 检查 Python 依赖
- 定期运行 `npm audit` 检查前端依赖
- 及时更新依赖到最新安全版本
