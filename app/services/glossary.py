"""Technology glossary correction for ASR and translated captions."""

import re
from dataclasses import dataclass
from typing import Iterable

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
CJK_CHAR_RE = r"[\u3400-\u4dbf\u4e00-\u9fff]"
LATIN_TERM_RE = r"[A-Za-z0-9][A-Za-z0-9+/#._-]*"


@dataclass(frozen=True)
class GlossaryRule:
    replacement: str
    aliases: tuple[str, ...]


SOURCE_RULES = (
    GlossaryRule(
        "API Gateway",
        ("API Gateway", "api gateway", "api 网关", "API 网关", "接口网关", "介面网关"),
    ),
    GlossaryRule(
        "REST API", ("REST API", "rest api", "Rest API", "RESTful API", "restful api")
    ),
    GlossaryRule("OpenAPI", ("Open API", "open api", "OpenAPI", "swagger", "Swagger")),
    GlossaryRule(
        "CI/CD", ("CI/CD", "ci/cd", "CI CD", "ci cd", "CI-CD", "c i / c d", "c i c d")
    ),
    GlossaryRule("OAuth", ("OAuth", "Oauth", "O Auth", "o auth", "欧auth", "欧授权")),
    GlossaryRule(
        "OpenID Connect", ("OpenID Connect", "open id connect", "OIDC", "O I D C")
    ),
    GlossaryRule("WebSocket", ("WebSocket", "web socket", "websocket", "Web Socket")),
    GlossaryRule("GraphQL", ("GraphQL", "graph ql", "Graph QL", "graphql")),
    GlossaryRule("gRPC", ("gRPC", "grpc", "G R P C")),
    GlossaryRule("PostgreSQL", ("PostgreSQL", "postgresql", "Postgres", "postgres")),
    GlossaryRule("SQL Server", ("SQL Server", "sql server", "MSSQL", "MS SQL")),
    GlossaryRule(
        "Elasticsearch",
        ("Elasticsearch", "elastic search", "Elastic Search", "elastic"),
    ),
    GlossaryRule("RabbitMQ", ("RabbitMQ", "rabbit mq", "Rabbit MQ")),
    GlossaryRule("Kubernetes", ("Kubernetes", "kubernetes", "k8s", "K8S", "K 8 S")),
    GlossaryRule("Bitbucket", ("Bitbucket", "bit bucket", "Bit Bucket")),
    GlossaryRule("Confluence", ("Confluence", "confluence")),
    GlossaryRule("Prometheus", ("Prometheus", "prometheus")),
    GlossaryRule("Grafana", ("Grafana", "grafana")),
    GlossaryRule("Swagger", ("Swagger UI", "swagger ui", "Swagger")),
    GlossaryRule(
        "UAT",
        (
            "UAT",
            "U A T",
            "优爱踢",
            "优艾踢",
            "優愛踢",
            "用户验收测试",
            "使用者验收测试",
        ),
    ),
    GlossaryRule(
        "SIT", ("SIT", "S I T", "艾斯爱踢", "艾斯艾踢", "系统整合测试", "系统集成测试")
    ),
    GlossaryRule("DEV", ("DEV", "Dev", "dev", "development environment", "开发环境")),
    GlossaryRule(
        "STG", ("STG", "Staging", "staging", "stage environment", "staging environment")
    ),
    GlossaryRule(
        "PROD",
        (
            "PROD",
            "Prod",
            "prod",
            "PRD",
            "production",
            "production environment",
            "正式环境",
            "生产环境",
        ),
    ),
    GlossaryRule("DR", ("DR environment", "DR", "disaster recovery", "灾备环境")),
    GlossaryRule("ITKM", ("ITKM", "IT KM", "爱踢KM", "爱踢 K M", "艾踢KM", "愛踢KM")),
    GlossaryRule(
        "KKday",
        (
            "KKday",
            "KKDAY",
            "KK Day",
            "kk day",
            "开开大",
            "开开 day",
            "开开代",
            "開開大",
            "kKDE",
        ),
    ),
    GlossaryRule(
        "O2P",
        (
            "O2P",
            "O 2 P",
            "O two P",
            "欧土坯",
            "欧吐皮",
            "欧图皮",
            "欧兔皮",
            "欧二批",
            "歐土坯",
        ),
    ),
    GlossaryRule("OBIT", ("OBIT", "Obit", "欧比特", "欧必特", "歐比特")),
    GlossaryRule("DDI", ("DDI", "D D I", "滴滴")),
    GlossaryRule("CRS", ("CRS", "C R S", "西阿尔艾斯", "西阿爾艾斯")),
    GlossaryRule("ABI", ("ABI", "A B I")),
    GlossaryRule("NGNTS", ("NGNTS", "N G N T S")),
    GlossaryRule("SASD", ("SASD", "S A S D")),
    GlossaryRule("MGNT", ("MGNT", "M G N T")),
    GlossaryRule("TOP", ("TOP", "T O P")),
    GlossaryRule("FTB", ("FTB", "F T B")),
    GlossaryRule(
        "IT",
        (
            "IT",
            "I T",
            "爱踢",
            "艾踢",
            "挨踢",
            "爱提",
            "艾提",
            "愛踢",
            "资讯单位",
            "資訊單位",
        ),
    ),
    GlossaryRule("PM", ("PM", "P M", "皮炎", "皮恩", "批恩", "披恩", "皮 M", "批 M")),
    GlossaryRule("PO", ("PO", "P O", "皮欧", "批欧", "披欧")),
    GlossaryRule("BA", ("BA", "B A", "比诶", "比欸")),
    GlossaryRule("SA", ("SA", "S A", "诶斯诶", "艾斯诶")),
    GlossaryRule("QA", ("QA", "Q A", "cue A", "丘 A", "球 A")),
    GlossaryRule("QC", ("QC", "Q C", "cue C", "丘 C", "球 C")),
    GlossaryRule("RD", ("RD", "R D", "阿尔迪", "阿爾迪")),
    GlossaryRule("DBA", ("DBA", "D B A")),
    GlossaryRule("PDF", ("PDF", "P D F", "批低欸夫", "披地爱夫", "屁地爱服")),
    GlossaryRule(
        "API", ("API", "A P I", "诶批爱", "欸批爱", "爱批爱", "埃皮爱", "接口")
    ),
    GlossaryRule("UI", ("UI", "U I", "优爱", "優愛")),
    GlossaryRule("UX", ("UX", "U X", "优艾克斯", "優艾克斯")),
    GlossaryRule("SQL", ("SQL", "S Q L", "sequel", "Sequel", "思扣", "西扣")),
    GlossaryRule("DB", ("DB", "D B", "低比", "低逼", "滴比", "数据库", "資料庫")),
    GlossaryRule("JSON", ("JSON", "J S O N", "json")),
    GlossaryRule("XML", ("XML", "X M L", "xml")),
    GlossaryRule("CSV", ("CSV", "C S V", "csv")),
    GlossaryRule("YAML", ("YAML", "Y A M L", "yaml", "yml", "YML")),
    GlossaryRule("JWT", ("JWT", "J W T", "jwt")),
    GlossaryRule("SSO", ("SSO", "S S O", "single sign on", "Single Sign On")),
    GlossaryRule("SAML", ("SAML", "S A M L", "saml")),
    GlossaryRule("LDAP", ("LDAP", "L D A P", "ldap")),
    GlossaryRule("RBAC", ("RBAC", "R B A C", "role based access control")),
    GlossaryRule("ACL", ("ACL", "A C L", "access control list")),
    GlossaryRule("IAM", ("IAM", "I A M", "identity access management")),
    GlossaryRule("MFA", ("MFA", "M F A", "multi factor authentication")),
    GlossaryRule("2FA", ("2FA", "2 F A", "two factor authentication")),
    GlossaryRule("OTP", ("OTP", "O T P", "one time password")),
    GlossaryRule("OCR", ("OCR", "O C R", "欧西阿尔", "歐西阿爾")),
    GlossaryRule("TLS", ("TLS", "T L S", "tls")),
    GlossaryRule("SSL", ("SSL", "S S L", "ssl")),
    GlossaryRule("HTTP", ("HTTP", "H T T P", "http")),
    GlossaryRule("HTTPS", ("HTTPS", "H T T P S", "https")),
    GlossaryRule("URL", ("URL", "U R L", "url")),
    GlossaryRule("URI", ("URI", "U R I", "uri")),
    GlossaryRule("DNS", ("DNS", "D N S", "dns")),
    GlossaryRule("CDN", ("CDN", "C D N", "cdn")),
    GlossaryRule("VPN", ("VPN", "V P N", "vpn")),
    GlossaryRule("VPC", ("VPC", "V P C", "vpc")),
    GlossaryRule("CPU", ("CPU", "C P U", "cpu")),
    GlossaryRule("GPU", ("GPU", "G P U", "gpu")),
    GlossaryRule("RAM", ("RAM", "R A M", "ram")),
    GlossaryRule("ROM", ("ROM", "R O M", "rom")),
    GlossaryRule("SSD", ("SSD", "S S D", "ssd")),
    GlossaryRule("HDD", ("HDD", "H D D", "hdd")),
    GlossaryRule("OS", ("OS", "O S", "os")),
    GlossaryRule("VM", ("VM", "V M", "virtual machine")),
    GlossaryRule("SDK", ("SDK", "S D K", "sdk")),
    GlossaryRule("IDE", ("IDE", "I D E", "ide")),
    GlossaryRule("CLI", ("CLI", "C L I", "command line interface")),
    GlossaryRule("GUI", ("GUI", "G U I", "gui")),
    GlossaryRule("CRUD", ("CRUD", "C R U D", "crud")),
    GlossaryRule("ETL", ("ETL", "E T L", "etl")),
    GlossaryRule("ELT", ("ELT", "E L T", "elt")),
    GlossaryRule("DWH", ("DWH", "D W H", "data warehouse")),
    GlossaryRule("BI", ("BI", "B I", "business intelligence")),
    GlossaryRule("OLTP", ("OLTP", "O L T P", "oltp")),
    GlossaryRule("OLAP", ("OLAP", "O L A P", "olap")),
    GlossaryRule("MQ", ("MQ", "M Q", "message queue")),
    GlossaryRule("SMTP", ("SMTP", "S M T P", "smtp")),
    GlossaryRule("SFTP", ("SFTP", "S F T P", "sftp")),
    GlossaryRule("FTP", ("FTP", "F T P", "ftp")),
    GlossaryRule("SMS", ("SMS", "S M S", "sms")),
    GlossaryRule("AWS", ("AWS", "A W S", "aws")),
    GlossaryRule("Azure", ("Azure", "azure", "阿祖尔", "阿朱尔")),
    GlossaryRule("GCP", ("GCP", "G C P", "Google Cloud Platform")),
    GlossaryRule("Docker", ("Docker", "docker", "多克尔", "多克")),
    GlossaryRule("Nginx", ("Nginx", "nginx", "engine x", "Engine X")),
    GlossaryRule("Redis", ("Redis", "redis")),
    GlossaryRule("Kafka", ("Kafka", "kafka", "卡夫卡")),
    GlossaryRule("MySQL", ("MySQL", "mysql", "My SQL", "my sql")),
    GlossaryRule("MongoDB", ("MongoDB", "mongo db", "Mongo DB")),
    GlossaryRule("Oracle DB", ("Oracle DB", "oracle db", "Oracle database")),
    GlossaryRule("GitHub", ("GitHub", "github", "Git Hub", "git hub")),
    GlossaryRule("GitLab", ("GitLab", "gitlab", "Git Lab", "git lab")),
    GlossaryRule("Git", ("Git", "git")),
    GlossaryRule("Jira", ("Jira", "jira", "吉拉")),
    GlossaryRule("Jenkins", ("Jenkins", "jenkins")),
    GlossaryRule("Postman", ("Postman", "postman")),
    GlossaryRule("Figma", ("Figma", "figma", "菲格玛")),
    GlossaryRule("PR", ("PR", "P R", "pull request")),
    GlossaryRule("MR", ("MR", "M R", "merge request")),
    GlossaryRule("MVP", ("MVP", "M V P", "minimum viable product")),
    GlossaryRule("POC", ("POC", "P O C", "proof of concept")),
    GlossaryRule("WIP", ("WIP", "W I P", "work in progress")),
    GlossaryRule("ETA", ("ETA", "E T A", "埃塔", "艾塔")),
    GlossaryRule("SLA", ("SLA", "S L A", "service level agreement")),
    GlossaryRule("SLO", ("SLO", "S L O", "service level objective")),
    GlossaryRule("KPI", ("KPI", "K P I", "key performance indicator")),
    GlossaryRule("OKR", ("OKR", "O K R", "objective key result")),
    GlossaryRule("RCA", ("RCA", "R C A", "root cause analysis")),
    GlossaryRule("SOP", ("SOP", "S O P", "standard operating procedure")),
    GlossaryRule("SOW", ("SOW", "S O W", "statement of work")),
    GlossaryRule("ERP", ("ERP", "E R P", "enterprise resource planning")),
    GlossaryRule("CRM", ("CRM", "C R M", "customer relationship management")),
    GlossaryRule("CMS", ("CMS", "C M S", "content management system")),
    GlossaryRule("DMS", ("DMS", "D M S", "document management system")),
    GlossaryRule("POS", ("POS", "P O S", "point of sale")),
    GlossaryRule("OMS", ("OMS", "O M S", "order management system")),
    GlossaryRule("Frontend", ("Frontend", "front end", "frontend", "前端")),
    GlossaryRule("Backend", ("Backend", "back end", "backend", "后端", "後端")),
    GlossaryRule(
        "Full-stack", ("Full stack", "full stack", "fullstack", "全栈", "全端")
    ),
    GlossaryRule("microservice", ("microservice", "micro service", "微服务", "微服務")),
    GlossaryRule("monolith", ("monolith", "monolithic", "单体架构", "單體架構")),
    GlossaryRule("load balancer", ("load balancer", "负载均衡", "負載均衡")),
    GlossaryRule("reverse proxy", ("reverse proxy", "反向代理")),
    GlossaryRule("endpoint", ("endpoint", "end point", "端点", "端點")),
    GlossaryRule("webhook", ("webhook", "web hook")),
    GlossaryRule("token", ("token", "Token", "口令", "令牌")),
    GlossaryRule("certificate", ("certificate", "凭证", "憑證", "证书", "證書")),
    GlossaryRule("credential", ("credential", "credentials")),
    GlossaryRule("permission", ("permission", "permissions", "权限", "權限")),
    GlossaryRule("role", ("role", "roles", "角色")),
    GlossaryRule("access control", ("access control", "访问控制", "存取控制")),
    GlossaryRule("authentication", ("authentication", "身份验证", "身分驗證")),
    GlossaryRule("authorization", ("authorization", "授权", "授權")),
    GlossaryRule("encryption", ("encryption", "加密")),
    GlossaryRule("decryption", ("decryption", "解密")),
    GlossaryRule("hash", ("hash", "Hash", "哈希", "杂凑")),
    GlossaryRule("cache", ("cache", "Cache", "缓存", "快取")),
    GlossaryRule("session", ("session", "Session", "会话", "工作階段")),
    GlossaryRule("cookie", ("cookie", "Cookie")),
    GlossaryRule("cron job", ("cron job", "cron", "排程任务", "排程任務")),
    GlossaryRule("batch job", ("batch job", "批次作业", "批次作業")),
    GlossaryRule("scheduler", ("scheduler", "排程")),
    GlossaryRule("queue", ("queue", "Queue", "队列", "佇列")),
    GlossaryRule("worker", ("worker", "Worker")),
    GlossaryRule("deployment", ("deployment", "deploy", "部署")),
    GlossaryRule("release", ("release", "Release", "发布", "發布")),
    GlossaryRule("rollback", ("rollback", "Roll back", "回滚", "回復")),
    GlossaryRule("hotfix", ("hotfix", "Hotfix", "紧急修复", "緊急修復")),
    GlossaryRule("sprint", ("sprint", "Sprint")),
    GlossaryRule("backlog", ("backlog", "Backlog")),
    GlossaryRule("project", ("project", "Project", "专案", "專案", "项目", "項目")),
    GlossaryRule("ticket", ("ticket", "Ticket", "工单", "工單")),
    GlossaryRule("card", ("card", "Card", "卡片")),
    GlossaryRule("requirement", ("requirement", "requirements", "需求")),
    GlossaryRule("spec", ("spec", "Spec", "规格", "規格")),
    GlossaryRule("scope", ("scope", "Scope", "范围", "範圍")),
    GlossaryRule("timeline", ("timeline", "Timeline", "时程", "時程")),
    GlossaryRule("milestone", ("milestone", "Milestone", "里程碑")),
    GlossaryRule(
        "acceptance criteria", ("acceptance criteria", "验收条件", "驗收條件")
    ),
    GlossaryRule("test case", ("test case", "test cases", "测试案例", "測試案例")),
    GlossaryRule("unit test", ("unit test", "unit testing", "单元测试", "單元測試")),
    GlossaryRule(
        "integration test",
        ("integration test", "integration testing", "整合测试", "整合測試", "集成测试"),
    ),
    GlossaryRule(
        "regression test",
        ("regression test", "regression testing", "回归测试", "迴歸測試"),
    ),
    GlossaryRule(
        "automation test",
        ("automation test", "automated testing", "自动化测试", "自動化測試"),
    ),
    GlossaryRule("E2E test", ("E2E test", "end to end test", "end-to-end test")),
    GlossaryRule("invoice", ("invoice", "Invoice", "发票", "發票")),
    GlossaryRule("payment", ("payment", "Payment", "付款", "支付")),
    GlossaryRule("payment flow", ("payment flow", "金流")),
    GlossaryRule("credit card", ("credit card", "信用卡")),
    GlossaryRule(
        "third-party payment",
        ("third party payment", "third-party payment", "第三方支付"),
    ),
    GlossaryRule("blacklist", ("blacklist", "Black list", "黑名单", "黑名單")),
    GlossaryRule("whitelist", ("whitelist", "White list", "白名单", "白名單")),
    GlossaryRule("serial number", ("serial number", "serial no", "序号", "序號")),
    GlossaryRule("report", ("report", "Report", "报表", "報表")),
    GlossaryRule("dashboard", ("dashboard", "Dashboard", "仪表板", "儀表板")),
    GlossaryRule("link", ("link", "Link", "链接", "連結", "连接")),
    GlossaryRule(
        "edit feature", ("edit feature", "editing feature", "编辑功能", "編輯功能")
    ),
    GlossaryRule("go-live", ("go live", "go-live", "上线", "上線")),
    GlossaryRule("Albert", ("Albert", "albert", "阿尔伯特", "阿爾伯特")),
    GlossaryRule("Oscar", ("Oscar", "oscar", "奥斯卡", "奧斯卡")),
    GlossaryRule("Aska", ("Aska", "aska", "阿斯卡", "阿司卡")),
    GlossaryRule("Jason", ("Jason", "jason", "杰森")),
    GlossaryRule("Kevin", ("Kevin", "kevin", "凯文", "凱文")),
    GlossaryRule("Christian", ("Christian", "christian", "克里斯蒂安", "克里斯")),
    GlossaryRule("RRA", ("RRA", "rra", "瑞瑞安", "瑞瑞")),
)


SOURCE_PATTERNS = None


def apply_source_glossary(text: str, language_code: str = "") -> str:
    """Normalize source ASR text before it is shown or sent to translation."""
    corrected = _apply_patterns(text, _source_patterns())
    return _normalize_spacing(corrected)


def apply_translation_glossary(text: str, target_language: str = "") -> str:
    """Normalize translated text for domain terms that should stay stable."""
    return _normalize_spacing(text)


def _source_patterns():
    global SOURCE_PATTERNS
    if SOURCE_PATTERNS is None:
        SOURCE_PATTERNS = tuple(_compile_rules(SOURCE_RULES))
    return SOURCE_PATTERNS


def _compile_rules(rules: Iterable[GlossaryRule]):
    for rule in rules:
        for alias in sorted(rule.aliases, key=len, reverse=True):
            yield re.compile(_alias_pattern(alias), re.IGNORECASE), rule.replacement


def _alias_pattern(alias: str) -> str:
    clean_alias = str(alias or "").strip()
    if not clean_alias:
        return r"$^"
    if CJK_RE.search(clean_alias):
        return _cjk_alias_pattern(clean_alias)
    return _latin_alias_pattern(clean_alias)


def _cjk_alias_pattern(alias: str) -> str:
    pieces = [re.escape(char) for char in alias if not char.isspace()]
    return r"(?<![A-Za-z0-9])" + r"\s*".join(pieces) + r"(?![A-Za-z0-9])"


def _latin_alias_pattern(alias: str) -> str:
    escaped = re.escape(alias)
    escaped = escaped.replace(r"\ ", r"\s+")
    escaped = escaped.replace(r"\/", r"\s*/\s*")
    escaped = escaped.replace(r"\-", r"\s*-\s*")
    escaped = escaped.replace(r"\.", r"\s*\.\s*")
    return r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])"


def _apply_patterns(text: str, patterns) -> str:
    corrected = str(text or "").strip()
    if not corrected:
        return ""
    for pattern, replacement in patterns:
        corrected = pattern.sub(replacement, corrected)
    return corrected


def _normalize_spacing(text: str) -> str:
    clean_text = str(text or "").strip()
    if not clean_text:
        return ""
    clean_text = re.sub(
        rf"({CJK_CHAR_RE})({LATIN_TERM_RE})",
        r"\1 \2",
        clean_text,
    )
    clean_text = re.sub(
        rf"({LATIN_TERM_RE})({CJK_CHAR_RE})",
        r"\1 \2",
        clean_text,
    )
    clean_text = re.sub(r"[ \t]+", " ", clean_text)
    clean_text = re.sub(r"\s+([,.;:!?])", r"\1", clean_text)
    return clean_text.strip()
