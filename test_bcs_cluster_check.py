#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试BCS集群关联状态检测命令

这个脚本用于验证check_bcs_cluster_status命令的基本功能。
可以在开发环境中运行，确保命令能够正常工作。
"""

import os
import sys
import django
import json
from io import StringIO

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
django.setup()

from django.core.management import call_command
from django.test import TestCase
from metadata.models.bcs.cluster import BCSClusterInfo


def test_command_help():
    """测试命令帮助信息"""
    print("=" * 60)
    print("测试命令帮助信息")
    print("=" * 60)
    
    try:
        out = StringIO()
        call_command('check_bcs_cluster_status', '--help', stdout=out)
        print("✓ 命令帮助信息正常")
        return True
    except Exception as e:
        print(f"✗ 命令帮助信息异常: {e}")
        return False


def test_missing_cluster_id():
    """测试缺少cluster-id参数"""
    print("\n" + "=" * 60)
    print("测试缺少cluster-id参数")
    print("=" * 60)
    
    try:
        out = StringIO()
        err = StringIO()
        call_command('check_bcs_cluster_status', stdout=out, stderr=err)
        print("✗ 应该抛出参数错误")
        return False
    except SystemExit:
        print("✓ 正确检测到缺少必需参数")
        return True
    except Exception as e:
        print(f"✓ 正确抛出异常: {e}")
        return True


def test_nonexistent_cluster():
    """测试不存在的集群"""
    print("\n" + "=" * 60)
    print("测试不存在的集群")
    print("=" * 60)
    
    try:
        out = StringIO()
        call_command(
            'check_bcs_cluster_status',
            '--cluster-id', 'NONEXISTENT-CLUSTER',
            '--format', 'json',
            stdout=out
        )
        
        result = json.loads(out.getvalue())
        if result.get('status') == 'NOT_FOUND':
            print("✓ 正确检测到集群不存在")
            return True
        else:
            print(f"✗ 期望状态NOT_FOUND，实际状态: {result.get('status')}")
            return False
            
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False


def test_existing_cluster():
    """测试存在的集群（如果数据库中有的话）"""
    print("\n" + "=" * 60)
    print("测试存在的集群")
    print("=" * 60)
    
    try:
        # 查找数据库中的第一个集群
        cluster = BCSClusterInfo.objects.first()
        if not cluster:
            print("⚠ 数据库中没有集群记录，跳过此测试")
            return True
        
        cluster_id = cluster.cluster_id
        print(f"测试集群: {cluster_id}")
        
        out = StringIO()
        call_command(
            'check_bcs_cluster_status',
            '--cluster-id', cluster_id,
            '--format', 'json',
            stdout=out
        )
        
        result = json.loads(out.getvalue())
        status = result.get('status')
        
        print(f"检测结果状态: {status}")
        print(f"执行时间: {result.get('execution_time', 0)}秒")
        
        # 检查返回的数据结构
        required_keys = ['cluster_id', 'check_time', 'status', 'details', 'execution_time']
        missing_keys = [key for key in required_keys if key not in result]
        
        if missing_keys:
            print(f"✗ 返回数据缺少字段: {missing_keys}")
            return False
        
        # 检查详细信息结构
        details = result.get('details', {})
        expected_components = ['database', 'bcs_api', 'kubernetes', 'datasources', 'monitor_resources']
        missing_components = [comp for comp in expected_components if comp not in details]
        
        if missing_components:
            print(f"⚠ 缺少检测组件: {missing_components}")
        
        print("✓ 集群检测命令执行成功")
        return True
        
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False


def test_text_format_output():
    """测试文本格式输出"""
    print("\n" + "=" * 60)
    print("测试文本格式输出")
    print("=" * 60)
    
    try:
        # 查找数据库中的第一个集群
        cluster = BCSClusterInfo.objects.first()
        if not cluster:
            print("⚠ 数据库中没有集群记录，跳过此测试")
            return True
        
        cluster_id = cluster.cluster_id
        
        out = StringIO()
        call_command(
            'check_bcs_cluster_status',
            '--cluster-id', cluster_id,
            '--format', 'text',
            stdout=out
        )
        
        output = out.getvalue()
        
        # 检查输出是否包含预期的内容
        expected_content = [
            "BCS集群关联状态检测报告",
            f"集群ID: {cluster_id}",
            "检测时间:",
            "执行时间:",
            "整体状态:",
        ]
        
        missing_content = [content for content in expected_content if content not in output]
        
        if missing_content:
            print(f"✗ 输出缺少内容: {missing_content}")
            return False
        
        print("✓ 文本格式输出正常")
        return True
        
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False


def test_timeout_parameter():
    """测试超时参数"""
    print("\n" + "=" * 60)
    print("测试超时参数")
    print("=" * 60)
    
    try:
        out = StringIO()
        call_command(
            'check_bcs_cluster_status',
            '--cluster-id', 'NONEXISTENT-CLUSTER',
            '--timeout', '5',
            '--format', 'json',
            stdout=out
        )
        
        result = json.loads(out.getvalue())
        if 'execution_time' in result:
            print("✓ 超时参数正常工作")
            return True
        else:
            print("✗ 超时参数未生效")
            return False
            
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False


def main():
    """主测试函数"""
    print("开始测试BCS集群关联状态检测命令")
    print("测试环境:", os.environ.get('DJANGO_SETTINGS_MODULE', '未设置'))
    
    test_results = []
    
    # 执行所有测试
    test_functions = [
        test_command_help,
        test_missing_cluster_id,
        test_nonexistent_cluster,
        test_existing_cluster,
        test_text_format_output,
        test_timeout_parameter,
    ]
    
    for test_func in test_functions:
        try:
            result = test_func()
            test_results.append((test_func.__name__, result))
        except Exception as e:
            print(f"测试 {test_func.__name__} 发生异常: {e}")
            test_results.append((test_func.__name__, False))
    
    # 输出测试结果摘要
    print("\n" + "=" * 60)
    print("测试结果摘要")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in test_results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {len(test_results)} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")
    
    if failed == 0:
        print("\n🎉 所有测试通过！命令功能正常")
        return 0
    else:
        print(f"\n⚠ 有 {failed} 个测试失败，请检查命令实现")
        return 1


if __name__ == '__main__':
    sys.exit(main())