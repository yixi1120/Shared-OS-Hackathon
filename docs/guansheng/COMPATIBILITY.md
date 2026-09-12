# V4 字体兼容修订说明

本版统一使用 Noto Sans SC，正文、标题、表头、页码及中西文字体槽均明确设置。Word 内嵌完整常规与粗体静态 TrueType 字体；PDF 已检查全部字形内置（Type3 字形程序及 Unicode 映射），不依赖系统中文字体。表格完整保留在一页，行高随内容增长；取消易漂移的字体主题继承，段落不在页中拆开，标题跟随正文。

修订后的 Word 经 LibreOffice 导出，10页均已逐页检查。PDF 使用 Poppler 与独立 PDFium 渲染复核。已核对 Word、PDF、Markdown、Dashboard 和提交文案均为95项代码测试、39项本地HTTP合同检查、9项浏览器检查；本次是字体与文档核对，没有将既有测试记录冒充新一轮完整运行。

分享与打印请优先使用同名 PDF；编辑使用 Word，并保留“在文件中嵌入字体”设置。未实测另一台实体电脑及全部 Word/WPS 版本，不能保证不支持嵌入字体的旧阅读器完全一致；此类环境使用 PDF 查看即可保持固定版面。不要再从旧版截图重新生成文档。

正式信息仍以 submission.json 为唯一来源。当前线上地址、正式seat ID、principal ID、Agent address等未齐全，不更新成已正式提交，不使用QA记录代填。信息补齐后运行仓库 check_submission.py，核对真实值，再更新提交正文和导出件。

技术依据：https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/1663dabc-5d98-463f-889e-bcd9b77c3d34
