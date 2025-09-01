#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BCS集群状态检查增强功能测试脚本

该脚本用于测试增强后的check_bcs_cluster_status.py命令的各项检查功能
"""

import json
import subprocess
import sys
from typing import Dict, Any

def run_cluster_check(cluster_id: str, format_type: str = "json", timeout: int = 30) -> Dict[str, Any]:
    """
    运行BCS集群状态检查命令
    
    Args:
        cluster_id: BCS集群ID
        format_type: 输出格式 (json/text)
        timeout: 超时时间
        
    Returns:
        检查结果字典
    """
    try:
        cmd = [
            "python", "bkmonitor/manage.py", 
            "check_bcs_cluster_status", 
            "--cluster-id", cluster_id,
            "--format", format_type,
            "--timeout", str(timeout)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        
        if result.returncode != 0:
            print(f"命令执行失败: {result.stderr}")
            return {"error": result.stderr}
        
        if format_type == "json":
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as e:
                print(f"JSON解析失败: {e}")
                return {"error": f"JSON解析失败: {e}", "raw_output": result.stdout}
        else:
            return {"text_output": result.stdout}
            
    except subprocess.TimeoutExpired:
        return {"error": "命令执行超时"}
    except Exception as e:
        return {"error": f"执行异常: {str(e)}"}

def analyze_check_results(check_result: Dict[str, Any]) -> None:
    """
    分析检查结果并输出摘要
    
    Args:
        check_result: 检查结果字典
    """
    if "error" in check_result:
        print(f"❌ 检查执行失败: {check_result['error']}")
        return
    
    if "text_output" in check_result:
        print("📝 文本格式输出:")
        print(check_result["text_output"])
        return
    
    # 分析JSON格式结果
    cluster_id = check_result.get("cluster_id", "未知")
    status = check_result.get("status", "UNKNOWN")
    execution_time = check_result.get("execution_time", 0)
    
    # 状态图标映射
    status_icons = {
        "SUCCESS": "✅",
        "WARNING": "⚠️", 
        "ERROR": "❌",
        "NOT_FOUND": "🔍",
        "UNKNOWN": "❓"
    }
    
    icon = status_icons.get(status, "❓")
    
    print(f"🔍 BCS集群检查结果摘要")
    print(f"📋 集群ID: {cluster_id}")
    print(f"{icon} 整体状态: {status}")
    print(f"⏱️ 执行时间: {execution_time}秒")
    print(f"📅 检查时间: {check_result.get('check_time', '未知')}")
    
    # 详细检查项统计
    details = check_result.get("details", {})
    if details:
        print(f"\n📊 检查项详情:")
        for component, result in details.items():
            if isinstance(result, dict) and "status" in result:
                comp_status = result["status"]
                comp_icon = status_icons.get(comp_status, "❓")
                component_name = {
                    "database": "数据库记录",
                    "bcs_api": "BCS API连接",
                    "kubernetes": "Kubernetes连接",
                    "datasources": "数据源配置",
                    "monitor_resources": "监控资源",
                    "storage": "存储集群",
                    "consul": "Consul配置",
                    "data_collection": "数据采集配置",
                    "federation": "联邦集群",
                    "routing": "数据路由",
                    "resource_usage": "资源使用情况"
                }.get(component, component)
                
                print(f"  {comp_icon} {component_name}: {comp_status}")
                
                # 显示具体问题
                if result.get("issues"):
                    for issue in result["issues"][:3]:  # 最多显示3个问题
                        print(f"    • {issue}")
    
    # 显示错误和警告
    errors = check_result.get("errors", [])
    warnings = check_result.get("warnings", [])
    
    if errors:
        print(f"\n❌ 错误信息:")
        for error in errors:
            print(f"  • {error}")
    
    if warnings:
        print(f"\n⚠️ 警告信息:")
        for warning in warnings:
            print(f"  • {warning}")

def main():
    """主函数"""
    print("🚀 BCS集群状态检查增强功能测试")
    print("=" * 50)
    
    # 从命令行参数获取集群ID，或使用默认测试ID
    if len(sys.argv) > 1:
        cluster_id = sys.argv[1]
    else:
        # 使用一个示例集群ID（实际环境中需要替换为真实的集群ID）
        cluster_id = "BCS-K8S-00001"
        print(f"ℹ️ 未提供集群ID参数，使用默认测试ID: {cluster_id}")
    
    print(f"🎯 正在检查集群: {cluster_id}")
    print("⏳ 执行增强的集群状态检查...")
    
    # 执行检查
    check_result = run_cluster_check(cluster_id, format_type="json", timeout=60)
    
    # 分析结果
    analyze_check_results(check_result)
    
    print("\n" + "=" * 50)
    print("✅ 测试完成")
    
    # 如果需要，也可以输出原始JSON结果
    if "--debug" in sys.argv:
        print("\n🔧 调试信息 - 原始JSON结果:")
        print(json.dumps(check_result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()