import json
import os
from collections import Counter

def check_duplicates():
    geojson_dir = "./dist/geojson/"
    line_names = []
    
    # 1. 遍历目录下所有文件
    if not os.path.exists(geojson_dir):
        print(f"Directory not found: {geojson_dir}")
        return

    for filename in os.listdir(geojson_dir):
        if not filename.endswith(".geojson"):
            continue
            
        filepath = os.path.join(geojson_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 2. 提取 Line 名称
            if "features" in data:
                for feature in data["features"]:
                    props = feature.get("properties", {})
                    # 仅检查类型为 line 的要素
                    if props.get("type") == "line":
                        name = props.get("name")
                        if name:
                            line_names.append(name)
                            
        except Exception as e:
            print(f"Error reading {filename}: {e}")

    # 3. 统计重复
    counter = Counter(line_names)
    duplicates = {name: count for name, count in counter.items() if count > 1}

    # 4. 输出结果
    print(f"\nTotal lines scanned: {len(line_names)}")
    print("-" * 40)
    
    if duplicates:
        print(f"Found {len(duplicates)} duplicate names:")
        for name, count in sorted(duplicates.items(), key=lambda x: x[1], reverse=True):
            print(f"  [{count}] {name}")
    else:
        print("No duplicate line names found.")

if __name__ == "__main__":
    check_duplicates()