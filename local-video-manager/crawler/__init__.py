"""视频元数据爬虫流水线（与 Flask 主程序解耦，由 app 注册路由）。"""

from crawler.flask_routes import CrawlerFlaskDeps, register_crawler_routes
from crawler.pipeline import run_pipeline

__all__ = ["CrawlerFlaskDeps", "register_crawler_routes", "run_pipeline"]
