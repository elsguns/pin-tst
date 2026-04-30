/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class CronRunningIndicator extends Component {
    static template = "running_scheduled_actions.CronRunningIndicator";
    static props = ["*"];

    get isRunning() {
        return !!this.props.record.data[this.props.name];
    }
}

registry.category("fields").add("cron_running_indicator", {
    component: CronRunningIndicator,
    supportedTypes: ["boolean"],
});
