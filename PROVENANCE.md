# 项目来源与证据留存说明

本文件用于记录项目作者身份、形成过程和提交边界。它不能替代正式法律意见，
但有助于在发生署名、复用或归属争议时说明项目来源。

## 可核验材料

- 课程平台或提交系统中的上传记录、提交时间、账号和附件。
- 本地项目文件的创建/修改时间、目录结构、README、docs、evaluation 和 tests。
- Git 提交历史、分支、提交作者、提交时间和差异记录。
- 运行日志、评测报告、截图、导出的数据库/三元组/叙事块文件。
- 与项目开发相关的聊天记录、调试记录、演示视频、压缩包和备份文件。
- AUTHORSHIP.md、LICENSE、NOTICE、README.md 中的作者、课程和提交边界说明。

## 提交前建议

- 在 AUTHORSHIP.md 中填写真实姓名、学号、班级、提交日期和联系方式。
- 保留一份提交前的完整压缩包，文件名包含姓名、课程、项目名和日期。
- 保留课程平台上传后的回执、截图或邮件通知。
- 若使用 Git，保留 `.git` 目录或导出提交记录截图。
- 不要删除 LICENSE、NOTICE、AUTHORSHIP.md 和 PROVENANCE.md。

## 可选校验命令

在 PowerShell 中可用以下命令生成文件清单和哈希，便于以后证明提交版本：

```powershell
Get-ChildItem -Recurse -File |
  Where-Object { $_.FullName -notmatch '\\venv\\|\\.git\\|__pycache__|\\.pytest_cache' } |
  Get-FileHash -Algorithm SHA256 |
  Export-Csv ".\submission_hashes.csv" -NoTypeInformation -Encoding UTF8
```

生成的 `submission_hashes.csv` 可以与提交压缩包一起留存，不需要公开给无关人员。
