/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";

/**
 * Equipment Barcode Scanner Component
 * Uses device camera to scan QR codes and barcodes
 */
export class EquipmentBarcodeScanner extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        
        this.state = useState({
            scanning: false,
            lastScanned: null,
            equipment: null,
            error: null,
            cameraActive: false,
        });

        this.videoRef = useRef("video");
        this.canvasRef = useRef("canvas");
        this.stream = null;
        this.scanInterval = null;

        onMounted(() => {
            this.startCamera();
        });

        onWillUnmount(() => {
            this.stopCamera();
        });
    }

    /**
     * Start camera and begin scanning
     */
    async startCamera() {
        try {
            // Request camera permission
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { 
                    facingMode: "environment",  // Use back camera on mobile
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            });

            const video = this.videoRef.el;
            if (video) {
                video.srcObject = this.stream;
                video.setAttribute("playsinline", true);
                await video.play();
                
                this.state.cameraActive = true;
                this.state.error = null;
                
                // Start scanning loop
                this.startScanning();
            }
        } catch (error) {
            console.error("Camera error:", error);
            this.state.error = "Unable to access camera. Please check permissions.";
            this.state.cameraActive = false;
        }
    }

    /**
     * Stop camera stream
     */
    stopCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.scanInterval) {
            clearInterval(this.scanInterval);
            this.scanInterval = null;
        }
        this.state.cameraActive = false;
    }

    /**
     * Start continuous scanning
     */
    startScanning() {
        this.scanInterval = setInterval(() => {
            this.scanFrame();
        }, 500);  // Scan every 500ms
    }

    /**
     * Scan a single frame for barcodes
     * Uses Odoo's native barcode detection or falls back to manual processing
     */
    async scanFrame() {
        if (!this.state.cameraActive || this.state.scanning) {
            return;
        }

        const video = this.videoRef.el;
        const canvas = this.canvasRef.el;
        
        if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) {
            return;
        }

        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        // Try to detect barcode using browser's native API if available
        if ('BarcodeDetector' in window) {
            try {
                const barcodeDetector = new BarcodeDetector({
                    formats: ['qr_code', 'code_128', 'code_39', 'ean_13', 'ean_8']
                });
                const barcodes = await barcodeDetector.detect(canvas);
                
                if (barcodes.length > 0) {
                    await this.onBarcodeDetected(barcodes[0].rawValue);
                }
            } catch (error) {
                console.error("Barcode detection error:", error);
            }
        } else {
            // Fallback: Use Odoo's barcode handler
            // This requires the user to manually enter or use a connected scanner
            console.log("Native barcode detection not available. Use manual entry or connected scanner.");
        }
    }

    /**
     * Handle detected barcode
     */
    async onBarcodeDetected(barcode) {
        if (this.state.scanning || this.state.lastScanned === barcode) {
            return;
        }

        this.state.scanning = true;
        this.state.lastScanned = barcode;

        try {
            // Search for equipment by barcode
            const equipment = await this.orm.searchRead(
                "equipment.item",
                [['barcode', '=', barcode]],
                ['name', 'state', 'category_id', 'location_id', 'custodian_id', 'barcode'],
                { limit: 1 }
            );

            if (equipment.length > 0) {
                this.state.equipment = equipment[0];
                this.state.error = null;
                
                // Play success sound
                this.playSuccessSound();
                
                // Show notification
                this.notification.add(
                    `Found: ${equipment[0].name}`,
                    { type: "success" }
                );

                // Auto-open equipment after 2 seconds
                setTimeout(() => {
                    this.openEquipment(equipment[0].id);
                }, 2000);
            } else {
                this.state.equipment = null;
                this.state.error = `No equipment found with barcode: ${barcode}`;
                this.playErrorSound();
                
                this.notification.add(
                    "Equipment not found",
                    { type: "warning" }
                );
            }
        } catch (error) {
            console.error("Search error:", error);
            this.state.error = "Error searching for equipment";
            this.playErrorSound();
        } finally {
            // Allow scanning again after 3 seconds
            setTimeout(() => {
                this.state.scanning = false;
                this.state.lastScanned = null;
            }, 3000);
        }
    }

    /**
     * Manual barcode entry
     */
    async onManualEntry(event) {
        if (event.key === 'Enter') {
            const barcode = event.target.value.trim();
            if (barcode) {
                await this.onBarcodeDetected(barcode);
                event.target.value = '';
            }
        }
    }

    /**
     * Open equipment form
     */
    openEquipment(equipmentId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'equipment.item',
            res_id: equipmentId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    /**
     * Quick borrow action
     */
    async quickBorrow() {
        if (!this.state.equipment) return;

        try {
            const result = await this.orm.call(
                "equipment.item",
                "action_borrow",
                [this.state.equipment.id]
            );
            
            if (result) {
                this.action.doAction(result);
            }
        } catch (error) {
            console.error("Borrow error:", error);
            this.notification.add(
                "Error creating loan",
                { type: "danger" }
            );
        }
    }

    /**
     * Quick return action
     */
    async quickReturn() {
        if (!this.state.equipment) return;

        try {
            const result = await this.orm.call(
                "equipment.item",
                "action_return",
                [this.state.equipment.id]
            );
            
            if (result) {
                this.action.doAction(result);
            }
        } catch (error) {
            console.error("Return error:", error);
            this.notification.add(
                "Error processing return",
                { type: "danger" }
            );
        }
    }

    /**
     * Close scanner
     */
    close() {
        this.stopCamera();
        this.action.doAction({ type: 'ir.actions.act_window_close' });
    }

    /**
     * Play success sound
     */
    playSuccessSound() {
        // Optional: Add success beep sound
        const audio = new Audio('/equipment_management/static/src/sounds/beep_success.wav');
        audio.play().catch(() => {});
    }

    /**
     * Play error sound
     */
    playErrorSound() {
        // Optional: Add error beep sound
        const audio = new Audio('/equipment_management/static/src/sounds/beep_error.wav');
        audio.play().catch(() => {});
    }
}

EquipmentBarcodeScanner.template = "equipment_management.BarcodeScannerTemplate";

// Register the component as a client action
registry.category("actions").add("equipment_barcode_scanner", EquipmentBarcodeScanner);