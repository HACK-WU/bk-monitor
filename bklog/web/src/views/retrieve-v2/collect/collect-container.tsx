/*
 * Tencent is pleased to support the open source community by making
 * 蓝鲸智云PaaS平台 (BlueKing PaaS) available.
 *
 * Copyright (C) 2021 THL A29 Limited, a Tencent company.  All rights reserved.
 *
 * 蓝鲸智云PaaS平台 (BlueKing PaaS) is licensed under the MIT License.
 *
 * License for 蓝鲸智云PaaS平台 (BlueKing PaaS):
 *
 * ---------------------------------------------------
 * Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
 * documentation files (the "Software"), to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
 * to permit persons to whom the Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all copies or substantial portions of
 * the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
 * THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
 * CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
 * IN THE SOFTWARE.
 */

import { Component, Emit, Provide, Prop, Watch } from 'vue-property-decorator';
import { Component as tsc } from 'vue-tsx-support';

import { Exception } from 'bk-magic-vue';
import VueDraggable from 'vuedraggable';

import CollectGroup from './collect-group';
import { IGroupItem } from './collect-index';

import './collect-container.scss';

interface IProps {
  dataList: IGroupItem[];
  groupList: IGroupItem[];
  isSearchFilter: boolean;
  collectLoading: boolean;
  activeFavoriteID: number;
}

@Component
export default class CollectContainer extends tsc<IProps> {
  @Prop({ type: Array, required: true }) dataList: IGroupItem[];
  @Prop({ type: Array, required: true }) groupList: IGroupItem[];
  @Prop({ type: Boolean, default: false }) isSearchFilter: boolean;
  @Prop({ type: Boolean, default: false }) collectLoading: boolean;
  @Prop({ type: Number }) activeFavoriteID: number;

  collectGroupRefs: (CollectGroup | null)[] = [];

  dragList: IGroupItem[] = []; // 可拖拽的收藏列表

  get isSearchEmpty() {
    return this.isSearchFilter && !this.dataList.length;
  }

  @Provide('handleUserOperate')
  handleUserOperate(type: string, value?: any) {
    this.handleValueChange(type, value);
  }

  @Emit('change')
  handleValueChange(type: string, value: any) {
    return {
      type,
      value,
    };
  }
  // 使用 @Watch 装饰器监听 dragList 的变化
  @Watch('dragList', { immediate: true, deep: true })
  onDragListChange(newList: IGroupItem[]) {
    // 初始化或更新 collectGroupRefs 数组
    this.collectGroupRefs = newList.map(() => null);
  }

  handleMoveEnd() {
    const dragIDList = this.dragList.map(item => item.group_id);
    this.handleValueChange('drag-move-end', dragIDList);
  }
  handleMoveIng(e) {
    if (e.draggedContext.element.group_type === 'private') return false;
    if (e.draggedContext.element.group_type === 'unknown') return false;
    if (e.relatedContext.element.group_type === 'private') return false;
    if (e.relatedContext.element.group_type === 'unknown') return false;
    return true;
  }

  handleGroupIsHidden(hidden: boolean) {
    this.collectGroupRefs.forEach(groupRef => {
      if (groupRef && typeof groupRef.handleGroupIsHidden === 'function') {
        groupRef.handleGroupIsHidden(hidden);
      }
    });
  }

  @Watch('dataList', { deep: true, immediate: true })
  private handleWatchDataList() {
    this.dragList = JSON.parse(JSON.stringify(this.dataList));
  }
  // 新增方法来渲染空消息
  private renderEmptyMessage(emptyType) {
    return (
      <div class='data-empty'>
        <div class='empty-box'>
          <Exception
            class='exception-wrap-item exception-part'
            scene='part'
            type={emptyType}
          ></Exception>
        </div>
      </div>
    );
  }
  // eslint-disable-next-line @typescript-eslint/member-ordering
  render() {
    return (
      <div
        style='backgroundColor:#ebeef5'
        class='bklog-v3-retrieve-collect-container'
      >
        {this.$slots.default}
        <div
          class='group-container-new'
          v-bkloading={{ isLoading: this.collectLoading }}
        >
          {!this.isSearchEmpty ? (
            this.dragList.length ? (
              <VueDraggable
                vModel={this.dragList}
                animation='150'
                disabled={true}
                handle='.group-title'
                move={this.handleMoveIng}
                on-end={this.handleMoveEnd}
              >
                <transition-group>
                  {this.dragList.map((item, index) => (
                    <div key={item.group_id}>
                      <CollectGroup
                        ref={el => (this.collectGroupRefs[index] = el as CollectGroup | null)}
                        activeFavoriteID={this.activeFavoriteID}
                        collectItem={item}
                        groupList={this.groupList}
                        isSearchFilter={this.isSearchFilter}
                      ></CollectGroup>
                    </div>
                  ))}
                </transition-group>
              </VueDraggable>
            ) : (
              this.renderEmptyMessage('empty')
            )
          ) : (
            this.renderEmptyMessage('search-empty')
          )}
        </div>
      </div>
    );
  }
}
