import requests
import pymysql
import json
from typing import Dict, Any, List

# 数据库配置（需要根据实际情况修改）
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3306,
    'user': 'root',
    'password': 'cajC3RwR0wcCWEJsoth2',
    'database': 'vision_to_tag',
    'charset': 'utf8mb4'
}

def find_confidence_tags(data: Dict[str, Any]) -> List[str]:
    """
    递归查找所有confidence结构中的标签key
    """
    tags = []
    if isinstance(data, dict):
        if 'confidence' in data and isinstance(data['confidence'], dict):
            tags.extend(data['confidence'].keys())
        for value in data.values():
            tags.extend(find_confidence_tags(value))
    elif isinstance(data, list):
        for item in data:
            tags.extend(find_confidence_tags(item))
    return list(set(tags))  # 去重

def process_video_urls(file_path: str):
    # 连接数据库
    connection = pymysql.connect(**DB_CONFIG)
    
    try:
        with open(file_path, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]

        for url in urls:
            try:
                # 发送API请求
                response = requests.post(
                    'http://127.0.0.1:6011/api/v1/vision_to_tag/google',
                    json={'url': url},
                    timeout=60
                )

                # 处理失败情况
                if response.status_code != 200 or response.json().get('code') != 200:
                    with connection.cursor() as cursor:
                        sql = """INSERT INTO video_url (url, state)
                                 VALUES (%s, 2)
                                 ON DUPLICATE KEY UPDATE state = 2"""
                        cursor.execute(sql, (url,))
                    connection.commit()
                    continue

                # 处理成功情况
                res_data = response.json().get('data', {})
                tags = find_confidence_tags(res_data)

                # 保存到数据库
                with connection.cursor() as cursor:
                    sql = """INSERT INTO video_url (url, tag, state)
                             VALUES (%s, %s, 1)
                             ON DUPLICATE KEY UPDATE tag = VALUES(tag), state = 1"""
                    cursor.execute(sql, (url, json.dumps(tags, ensure_ascii=False)))
                connection.commit()

            except Exception as e:
                print(f"处理URL {url} 时出错: {str(e)}")
                # 记录失败状态
                with connection.cursor() as cursor:
                    sql = """INSERT INTO video_url (url, state)
                             VALUES (%s, 2)
                             ON DUPLICATE KEY UPDATE state = 2"""
                    cursor.execute(sql, (url,))
                connection.commit()

    finally:
        connection.close()

if __name__ == '__main__':
    # process_video_urls('video_urls.txt')  # 替换为你的txt文件路径
    # 递归提取标签
    data = """
{
    "visual_analysis": {
        "character_dimension": {
            "tags": ["女性","青年","匀称","白皙","微笑","自然","休闲","中长发","淡妆","无配饰"],
            "confidence": {
                "女性":0.99,
                "青年":0.95,
                "匀称":0.9,
                "白皙":0.9,
                "微笑":0.95,
                "自然":0.9,
                "休闲":0.95,
                "中长发":0.9,
                "淡妆":0.95,
                "无配饰":0.9
            },
            "related_tags": {
                "视觉联想": ["T恤", "学生气", "裸妆感"],
                "听觉印证": ["少女音", "美妆话题", "产品推荐"],
                "语义扩展": ["校园风", "护肤分享", "购物推荐"],
                "confidence": {
                    "T恤": 0.85, 
                    "少女音": 0.81, 
                    "护肤分享": 0.76 
                }
            }
        },
        "scene_dimension": {
            "tags": ["室内","家居","白天","简约","现代"],
            "confidence": {
                "室内":0.95,
                "家居":0.9,
                "白天":0.95,
                "简约":0.9,
                "现代":0.95
            },
            "related_tags": {
                "视觉联想": ["百叶窗", "白墙"],
                "听觉印证": ["安静", "轻柔的说话声"],
                "语义扩展": ["个人生活", "直播场景"],
                "confidence": {
                    "百叶窗": 0.86, 
                    "安静": 0.81, 
                    "个人生活": 0.76  
                }
            }
        },
        "screen_content": {
            "tags": ["产品出镜","产品特写","真人出镜","单人","真实环境","室内","出现字幕","品牌露出","手持产品"],
            "confidence": {
                "产品出镜":0.99,
                "产品特写":0.95,
                "真人出镜":0.98,
                "单人":0.9,
                "真实环境":0.9,
                "室内":0.95,
                "出现字幕":0.98,
                "品牌露出":0.9,
                "手持产品":0.99
            },
            "related_tags": {
                "视觉联想": ["包装展示", "成分说明"],
                "听觉印证": ["产品功能介绍", "促销信息"],
                "语义扩展": ["电商广告", "健康产品"],
                "confidence": {
                    "包装展示": 0.89,  
                    "产品功能介绍": 0.83, 
                    "电商广告": 0.79    
                }
            }
        },
        "image_type": {
            "tags": ["居中","正面拍摄","特写","自然","暖色调","自然光","正常画面","无后期处理","无动画"],
            "confidence": {
                "居中":0.95,
                "正面拍摄":0.9,
                "特写":0.95,
                "自然":0.9,
                "暖色调":0.95,
                "自然光":0.9,
                "正常画面":0.95,
                "无后期处理":0.95,
                "无动画":0.9
            },
            "related_tags": {
                "视觉联想": ["美妆教程", "产品评测"],
                "听觉印证": ["解说旁白", "产品音效"],
                "语义扩展": ["消费推荐", "真实展示"],
                "confidence": {
                    "美妆教程": 0.86,  
                    "解说旁白": 0.81, 
                    "消费推荐": 0.76 
                }
            }
        }
    },
    "key_moments": {
        "points": [
            {
                "timestamp": "00:00",
                "duration": "00:02",
                "type": "产品展示",
                "description": "女性展示减肥产品",
                "tags": ["产品展示","女性","减肥产品"],
                "importance": 0.9,
                "action_points": []
            }
        ],
        "highlights": {
            "product_show": ["00:00"],
            "value_props": [],
            "call_to_action": []
        }
    }
}
    """
    print(json.dumps(find_confidence_tags(json.loads(data)), ensure_ascii=False ))