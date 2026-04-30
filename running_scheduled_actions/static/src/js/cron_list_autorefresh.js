/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

const REFRESH_INTERVAL_MS = 3000;

function startCronAutoRefresh(component, shouldSkip) {
    let intervalId = null;
    onMounted(() => {
        intervalId = setInterval(async () => {
            if (document.hidden) {
                return;
            }
            if (shouldSkip()) {
                return;
            }
            try {
                await component.model.root.load();
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
        startCronAutoRefresh(this, () => !!this.model.root.editedRecord);
    },
});

patch(FormController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel !== "ir.cron") {
            return;
        }
        startCronAutoRefresh(this, () => {
            const root = this.model.root;
            if (!root || !root.resId) {
                return true; // new/unsaved record, nothing to reload
            }
            return !!root.isDirty;
        });
    },
});
