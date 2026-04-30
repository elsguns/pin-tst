/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUnmount } from "@odoo/owl";

const REFRESH_INTERVAL_MS = 1000;

async function refreshIsRunning(orm, records) {
    const ids = records.map((r) => r.resId).filter(Boolean);
    if (!ids.length) {
        return;
    }
    const data = await orm.silent.read("ir.cron", ids, ["is_running"]);
    const byId = Object.fromEntries(data.map((d) => [d.id, d.is_running]));
    for (const rec of records) {
        const newValue = byId[rec.resId];
        if (newValue === undefined || !rec.data) {
            continue;
        }
        if (rec.data.is_running === newValue) {
            continue;
        }
        rec.data.is_running = newValue;
        // Propagate to canonical store + reactive eval contexts so that
        // modifier expressions (e.g. invisible="... or is_running") on
        // form views and row decorations re-evaluate.
        if (rec._values) {
            rec._values.is_running = newValue;
        }
        if (rec.evalContext) {
            rec.evalContext.is_running = newValue;
        }
        if (rec.evalContextWithVirtualIds) {
            rec.evalContextWithVirtualIds.is_running = newValue;
        }
    }
}

function startCronAutoRefresh(getRecords, shouldSkip, orm) {
    let intervalId = null;
    onMounted(() => {
        intervalId = setInterval(async () => {
            if (document.hidden || shouldSkip()) {
                return;
            }
            const records = getRecords();
            if (!records.length) {
                return;
            }
            try {
                await refreshIsRunning(orm, records);
            } catch (_e) {
                // transient errors (e.g. navigation): ignore
            }
        }, REFRESH_INTERVAL_MS);
    });
    onWillUnmount(() => {
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
    });
}

patch(ListController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel !== "ir.cron") {
            return;
        }
        const orm = useService("orm");
        startCronAutoRefresh(
            () => this.model.root.records || [],
            () => !!this.model.root.editedRecord,
            orm,
        );
    },
});

patch(ListRenderer.prototype, {
    getRowClass(record) {
        const base = super.getRowClass(record);
        if (this.props.list.resModel === "ir.cron" && record.data.is_running) {
            return base + " o_cron_running_row";
        }
        return base;
    },
});

patch(FormController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel !== "ir.cron") {
            return;
        }
        const orm = useService("orm");
        startCronAutoRefresh(
            () => {
                const root = this.model.root;
                return root && root.resId ? [root] : [];
            },
            () => {
                const root = this.model.root;
                if (!root || !root.resId) {
                    return true;
                }
                return !!root.dirty;
            },
            orm,
        );
    },
});
