/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

const REFRESH_INTERVAL_MS = 3000;

patch(ListController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel !== "ir.cron") {
            return;
        }
        let intervalId = null;
        onMounted(() => {
            intervalId = setInterval(async () => {
                if (document.hidden) {
                    return;
                }
                if (this.model.root.editedRecord) {
                    return;
                }
                try {
                    await this.model.root.load();
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
    },
});
