import requests
import pandas as pd
from io import BytesIO
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def get_zz2000_constituents_with_weight(save_path: str = "data") -> pd.DataFrame:
    """
    从中证指数官网获取中证2000成分股（包含权重），保存到 Excel 文件，并返回 DataFrame
    :param save_path: 保存 Excel 文件的路径，默认为 "data"
    :return: pd.DataFrame
    """
    url = "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/cons/932000cons.xls"
    try:
        response = requests.get(url)
        response.raise_for_status()  # 抛出异常如果请求失败

        df = pd.read_excel(BytesIO(response.content))
        df.columns = [
            "日期",
            "指数代码",
            "指数名称",
            "指数英文名称",
            "成分券代码",
            "成分券名称",
            "成分券英文名称",
            "交易所",
            "交易所英文名称",
            "权重(%)"
        ]
        df["成分券代码"] = df["成分券代码"].astype(str).str.zfill(6)

        # 保存到 Excel 文件
        Path(save_path).mkdir(parents=True, exist_ok=True)  # 确保路径存在
        file_path = Path(save_path) / "zz2000_constituents.xls"
        df.to_excel(file_path, index=False)
        logger.info(f"中证2000成分股数据已保存到: {file_path}")

        return df
    except requests.exceptions.RequestException as e:
        logger.error(f"获取中证2000成分股数据失败: {str(e)}")
        return pd.DataFrame()
    except pd.errors.ExcelFileError as e:
        logger.error(f"读取Excel文件失败: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"处理中证2000成分股数据失败: {str(e)}")
        return pd.DataFrame()