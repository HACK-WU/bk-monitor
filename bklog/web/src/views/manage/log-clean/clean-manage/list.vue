<!--
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
-->

<template>
  <section
    class="log-clean-container"
    data-test-id="cleaningList_section_cleaningListBox"
  >
    <section class="top-operation">
      <bk-button
        class="fl"
        data-test-id="cleaningListBox_button_addNewCleaningList"
        theme="primary"
        @click="handleCreate"
      >
        {{ $t('新增') }}
      </bk-button>
      <div class="clean-search fr">
        <bk-input
          v-model="params.keyword"
          :clearable="true"
          :right-icon="'bk-icon icon-search'"
          data-test-id="cleaningListBox_input_searchCleaningList"
          @change="handleSearchChange"
          @enter="search"
        >
        </bk-input>
        <div
          class="operation-icon"
          v-bk-tooltips="$t('同步计算平台的结果')"
          @click="handleSync"
        >
          <span
            v-if="!syncLoading"
            class="bklog-icon bklog-tongbu"
          ></span>
          <span
            v-else
            class="loading"
          ></span>
        </div>
      </div>
    </section>
    <section class="log-clean-list">
      <bk-table
        ref="cleanTable"
        class="clean-table"
        v-bkloading="{ isLoading: isTableLoading }"
        :data="cleanList"
        :limit-list="pagination.limitList"
        :pagination="pagination"
        :size="size"
        data-test-id="cleaningListBox_table_cleaningListTable"
        @filter-change="handleFilterChange"
        @page-change="handlePageChange"
        @page-limit-change="handleLimitChange"
      >
        <bk-table-column
          :label="$t('名称')"
          :render-header="$renderHeader"
        >
          <template #default="props">
            {{ props.row.collector_config_name }}
          </template>
        </bk-table-column>
        <bk-table-column
          :label="$t('存储索引')"
          :render-header="$renderHeader"
        >
          <template #default="props">
            {{ props.row.result_table_id }}
          </template>
        </bk-table-column>
        <bk-table-column
          :filter-multiple="false"
          :filters="formatFilters"
          :label="$t('格式化方法')"
          :render-header="$renderHeader"
          class-name="filter-column"
          column-key="etl_config"
          prop="etl_config"
        >
          <template #default="props">
            {{ getFormatName(props.row) }}
          </template>
        </bk-table-column>
        <bk-table-column
          :label="$t('更新人')"
          :render-header="$renderHeader"
        >
          <template #default="props">
            {{ props.row.updated_by }}
          </template>
        </bk-table-column>
        <bk-table-column
          :label="$t('更新时间')"
          :render-header="$renderHeader"
        >
          <template #default="props">
            {{ props.row.updated_at }}
          </template>
        </bk-table-column>
        <bk-table-column
          :label="$t('操作')"
          :render-header="$renderHeader"
          :width="operateWidth"
        >
          <template #default="props">
            <div class="collect-table-operate">
              <!-- bkdata_auth_url不为null则表示需要跳转计算平台检索 -->
              <!-- 高级清洗授权 -->
              <bk-button
                v-if="props.row.bkdata_auth_url"
                class="mr10 king-button"
                theme="primary"
                text
                @click="handleAuth(props.row)"
              >
                {{ $t('授权') }}
              </bk-button>
              <!-- 检索 -->
              <log-button
                v-else
                ext-cls="mr10 king-button"
                :button-text="$t('检索')"
                :cursor-active="!(props.row.permission && props.row.permission[authorityMap.SEARCH_LOG_AUTH])"
                :disabled="!props.row.is_active || !props.row.index_set_id"
                :tips-conf="getTipText(props.row)"
                theme="primary"
                text
                @on-click="operateHandler(props.row, 'search')"
              >
              </log-button>
              <!-- 编辑 -->
              <bk-button
                class="mr10 king-button"
                v-cursor="{
                  active: !(props.row.permission && props.row.permission[authorityMap.MANAGE_COLLECTION_AUTH]),
                }"
                theme="primary"
                text
                @click.stop="operateHandler(props.row, 'edit')"
              >
                {{ $t('编辑') }}
              </bk-button>
              <!-- 删除 -->
              <log-button
                ext-cls="mr10 king-button"
                :button-text="$t('删除')"
                :cursor-active="!(props.row.permission && props.row.permission[authorityMap.MANAGE_COLLECTION_AUTH])"
                :disabled="props.row.etl_config === 'bkdata_clean'"
                :tips-conf="''"
                theme="primary"
                text
                @on-click="operateHandler(props.row, 'delete')"
              >
              </log-button>
            </div>
          </template>
        </bk-table-column>
        <template #empty>
          <div>
            <empty-status
              :empty-type="emptyType"
              @operation="handleOperation"
            />
          </div>
        </template>
      </bk-table>
    </section>
  </section>
</template>

<script>
  import { clearTableFilter } from '@/common/util';
  import EmptyStatus from '@/components/empty-status';
  import { mapGetters } from 'vuex';

  import * as authorityMap from '../../../../common/authority-map';

  export default {
    name: 'CleanList',
    components: {
      EmptyStatus,
    },
    data() {
      return {
        isTableLoading: true,
        size: 'small',
        syncLoading: false,
        pagination: {
          current: 1,
          count: 0,
          limit: 10,
          limitList: [10, 20, 50, 100],
        },
        cleanList: [],
        params: {
          keyword: '',
          etl_config: '',
        },
        emptyType: 'empty',
        isFilterSearch: false,
      };
    },
    computed: {
      ...mapGetters({
        spaceUid: 'spaceUid',
        bkBizId: 'bkBizId',
        globalsData: 'globals/globalsData',
      }),
      authorityMap() {
        return authorityMap;
      },
      formatFilters() {
        const { etl_config: etlConfig } = this.globalsData;
        const target = [];
        etlConfig?.forEach(data => {
          target.push({
            text: data.name,
            value: data.id,
          });
        });
        target.push(
          { text: this.$t('原始数据'), value: 'bk_log_text' },
          { text: this.$t('高级清洗'), value: 'bkdata_clean' },
        );
        return target;
      },
      operateWidth() {
        return this.$store.state.isEnLanguage ? '240' : '200';
      },
    },
    mounted() {
      this.search();
    },
    beforeUnmount() {
      // 清除定时器
      this.timer && clearInterval(this.timer);
    },
    methods: {
      search() {
        this.pagination.current = 1;
        this.requestData();
      },
      handleFilterChange(data) {
        Object.keys(data).forEach(item => {
          this.params[item] = data[item].join('');
        });
        this.isFilterSearch = Object.values(data).reduce((pre, cur) => ((pre += cur.length), pre), 0);
        this.pagination.current = 1;
        this.search();
      },
      /**
       * 分页变换
       * @param  {Number} page 当前页码
       * @return {[type]}      [description]
       */
      handlePageChange(page) {
        if (this.pagination.current !== page) {
          this.pagination.current = page;
          this.requestData();
        }
      },
      /**
       * 分页限制
       * @param  {Number} page 当前页码
       * @return {[type]}      [description]
       */
      handleLimitChange(page) {
        if (this.pagination.limit !== page) {
          this.pagination.current = 1;
          this.pagination.limit = page;
          this.requestData();
        }
      },
      requestData() {
        this.isTableLoading = true;
        this.emptyType = this.params.keyword || this.isFilterSearch ? 'search-empty' : 'empty';
        this.$http
          .request('clean/cleanList', {
            query: {
              ...this.params,
              bk_biz_id: this.bkBizId,
              page: this.pagination.current,
              pagesize: this.pagination.limit,
            },
          })
          .then(res => {
            const { data } = res;
            this.pagination.count = data.total;
            this.cleanList = data.list;
          })
          .catch(err => {
            console.warn(err);
            this.emptyType = '500';
          })
          .finally(() => {
            this.isTableLoading = false;
          });
      },
      handleCreate() {
        this.$router.push({
          name: 'clean-create',
          query: {
            spaceUid: this.$store.state.spaceUid,
          },
        });
      },
      async getOptionApplyData(paramData) {
        try {
          this.isTableLoading = true;
          const res = await this.$store.dispatch('getApplyData', paramData);
          this.$store.commit('updateAuthDialogData', res.data);
        } catch (err) {
          console.warn(err);
        } finally {
          this.isTableLoading = false;
        }
      },
      getTipText(row) {
        if (!row.is_active) {
          return '';
        }

        if (!row.index_set_id) {
          return '';
        }
      },
      operateHandler(row, operateType) {
        if (['edit', 'delete'].includes(operateType) && row.etl_config === 'bkdata_clean') {
          // 编辑、删除操作，高级清洗跳转计算平台
          const id = row.bk_data_id;
          const jumpUrl = `${window.BKDATA_URL}/#/data-access/data-detail/${id}/3`;
          window.open(jumpUrl, '_blank');
          return;
        }
        if (operateType === 'delete' && row.etl_config !== 'bkdata_clean') {
          const h = this.$createElement;
          this.$bkInfo({
            title: this.$t('确定要删除清洗：{n}？', { n: row.collector_config_name }),
            subHeader: h('div', this.$t('请注意！删除后不能恢复。')),
            type: 'warning',
            confirmLoading: true,
            confirmFn: async () => {
              try {
                const res = await this.$http.request('clean/deleteParsing', {
                  params: { collector_config_id: row.collector_config_id },
                });
                if (res.data) {
                  this.messageSuccess(this.$t('删除成功'));
                  this.search();
                }
              } catch (err) {
                console.warn(err);
              }
            },
            okText: this.$t('button-确定').replace('button-', ''),
            cancelText: this.$t('button-取消').replace('button-', ''),
          });
          return;
        }
        if (operateType === 'edit') {
          // 基础清洗
          if (!row.permission?.[authorityMap.MANAGE_COLLECTION_AUTH]) {
            // 管理权限
            return this.getOptionApplyData({
              action_ids: [authorityMap.MANAGE_COLLECTION_AUTH],
              resources: [
                {
                  type: 'collection',
                  id: row.collector_config_id,
                },
              ],
            });
          }
        }
        if (operateType === 'search') {
          if (!row.permission?.[authorityMap.SEARCH_LOG_AUTH]) {
            // 检索权限
            return this.getOptionApplyData({
              action_ids: [authorityMap.SEARCH_LOG_AUTH],
              resources: [
                {
                  type: 'indices',
                  id: row.index_set_id,
                },
              ],
            });
          }
        }

        let routeName = '';
        const params = {};
        const query = {};
        if (operateType === 'edit') {
          routeName = 'clean-edit';
          query.spaceUid = this.$store.state.spaceUid;
          query.editName = row.collector_config_name;
          params.collectorId = row.collector_config_id;
        } else if (operateType === 'search') {
          routeName = 'retrieve';
          params.indexId = row.index_set_id;
        }

        this.$router.push({
          name: routeName,
          params,
          query,
        });
      },
      getFormatName(row) {
        const cleantype = row.etl_config;
        const matchItem = this.formatFilters?.find(conf => {
          return conf.value === cleantype;
        });
        return matchItem ? matchItem.text : '';
      },
      // 计算平台授权跳转
      handleAuth({ bkdata_auth_url: authUrl, index_set_id: id }) {
        let redirectUrl = ''; // 数据平台授权地址
        if (process.env.NODE_ENV === 'development') {
          redirectUrl = `${authUrl}&redirect_url=${window.origin}/static/auth.html`;
        } else {
          let siteUrl = window.SITE_URL;
          if (siteUrl.startsWith('http')) {
            if (!siteUrl.endsWith('/')) siteUrl += '/';
            redirectUrl = `${authUrl}&redirect_url=${siteUrl}bkdata_auth/`;
          } else {
            if (!siteUrl.startsWith('/')) siteUrl = `/${siteUrl}`;
            if (!siteUrl.endsWith('/')) siteUrl += '/';
            redirectUrl = `${authUrl}&redirect_url=${window.origin}${siteUrl}bkdata_auth/`;
          }
        }
        // auth.html 返回清洗列表的路径
        const cleanPath = location.href.match(/http.*\/clean-list/)[0];
        // auth.html 需要使用的数据
        const urlComponent = `?indexSetId=${id}&ajaxUrl=${window.AJAX_URL_PREFIX}&redirectUrl=${cleanPath}`;
        redirectUrl += encodeURIComponent(urlComponent);
        if (self !== top) {
          // 当前页面是 iframe
          window.open(redirectUrl);
          this.returnIndexList();
        } else {
          window.location.assign(redirectUrl);
        }
      },
      // 同步计算平台结果表
      handleSync() {
        if (!this.syncLoading) {
          this.getSyncStatus();
        }
      },
      // 同步计算平台结果表
      getSyncStatus(isPolling = false) {
        this.syncLoading = true;
        this.$http
          .request('clean/sync', {
            query: {
              bk_biz_id: this.bkBizId,
              polling: isPolling,
            },
          })
          .then(res => {
            const { data } = res;
            if (data.status === 'DONE') {
              clearInterval(this.timer);
              this.timer = null;
              this.syncLoading = false;
              this.messageSuccess(this.$t('同步计算平台的结果表成功'));
              this.requestData();
            } else if (data.status === 'RUNNING') {
              // 轮循直至同步成功
              if (this.timer) {
                return 1;
              }
              this.timer = setInterval(() => {
                this.getSyncStatus(true);
              }, 2000);
            } else {
              this.messageError(this.$t('同步计算平台的结果表失败'));
              this.syncLoading = false;
            }
          })
          .catch(() => {
            this.syncLoading = false;
          });
      },
      handleSearchChange(val) {
        if (val === '' && !this.isTableLoading) {
          this.search();
        }
      },
      handleOperation(type) {
        if (type === 'clear-filter') {
          this.params.keyword = '';
          clearTableFilter(this.$refs.cleanTable);
          this.search();
          return;
        }

        if (type === 'refresh') {
          this.emptyType = 'empty';
          this.search();
          return;
        }
      },
    },
  };
</script>

<style lang="scss">
  @import '@/scss/mixins/clearfix';
  @import '@/scss/conf';
  @import '@/scss/devops-common.scss';

  .log-clean-container {
    padding: 20px 24px;

    .top-operation {
      margin-bottom: 20px;

      @include clearfix;

      .bk-button {
        width: 120px;
      }
    }

    .clean-search {
      display: flex;
      align-items: center;

      .bk-input-text {
        width: 320px;
      }

      .operation-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        min-width: 32px;
        height: 32px;
        margin-left: 10px;
        cursor: pointer;
        border: 1px solid #c4c6cc;
        border-radius: 2px;
        outline: none;
        transition: boder-color 0.2s;

        &:hover {
          border-color: #979ba5;
          transition: boder-color 0.2s;
        }

        &:active {
          border-color: #3a84ff;
          transition: boder-color 0.2s;
        }

        .icon-tongbu {
          font-size: 14px;
          color: #979ba5;
        }

        .loading {
          display: inline-block;
          width: 14px;
          height: 14px;
          margin: 0 auto;
          border: 2px solid #3a84ff;
          border-right: 2px solid transparent;
          border-radius: 50%;
          animation: button-icon-loading 1s linear infinite;
        }
      }
    }

    .clean-table {
      overflow: visible;

      .text-disabled {
        color: #c4c6cc;
      }

      .text-active {
        color: #3a84ff;
        cursor: pointer;
      }

      .filter-column {
        .cell {
          display: flex;
        }
      }
    }
  }
</style>
