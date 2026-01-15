# Compute Engine VM for GTFS Polling

# Startup script for the poller VM
locals {
  startup_script = <<-EOF
    #!/bin/bash
    set -e
    
    # Update system
    apt-get update
    apt-get install -y python3-pip python3-venv git
    
    # Create application directory
    mkdir -p /opt/gtfs-poller
    cd /opt/gtfs-poller
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Install dependencies (will be updated when deploying actual code)
    pip install --upgrade pip
    pip install google-cloud-pubsub requests protobuf gtfs-realtime-bindings
    
    # Create log directory
    mkdir -p /var/log/gtfs-poller
    
    # Create systemd service
    cat > /etc/systemd/system/gtfs-poller.service << 'SYSTEMD'
    [Unit]
    Description=GTFS-RT Poller for NYC Subway A/C/E
    After=network.target
    
    [Service]
    Type=simple
    User=root
    WorkingDirectory=/opt/gtfs-poller
    Environment=GOOGLE_CLOUD_PROJECT=${var.project_id}
    Environment=GTFS_TOPIC=${google_pubsub_topic.gtfs_rt.id}
    Environment=ALERTS_TOPIC=${google_pubsub_topic.service_alerts.id}
    ExecStart=/opt/gtfs-poller/venv/bin/python /opt/gtfs-poller/main.py
    Restart=always
    RestartSec=10
    StandardOutput=append:/var/log/gtfs-poller/stdout.log
    StandardError=append:/var/log/gtfs-poller/stderr.log
    
    [Install]
    WantedBy=multi-user.target
    SYSTEMD
    
    systemctl daemon-reload
    
    echo "Startup script completed. Deploy application code to /opt/gtfs-poller/"
  EOF
}

# Poller VM Instance
resource "google_compute_instance" "poller" {
  name         = "gtfs-poller-vm"
  machine_type = var.poller_machine_type
  zone         = var.zone

  tags = ["gtfs-poller", "allow-ssh"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"

    access_config {
      # Ephemeral external IP
    }
  }

  service_account {
    email  = google_service_account.poller.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = local.startup_script
  }

  labels = {
    environment = var.environment
    purpose     = "gtfs-polling"
  }

  # Allow the instance to be stopped for cost savings
  scheduling {
    preemptible       = false
    automatic_restart = true
  }

  depends_on = [
    google_project_service.apis,
    google_pubsub_topic.gtfs_rt,
    google_pubsub_topic.service_alerts
  ]
}

# Firewall rule for SSH access
resource "google_compute_firewall" "allow_ssh" {
  name    = "allow-ssh-gtfs-poller"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["allow-ssh"]
}

# Firewall rule for egress (to MTA API)
resource "google_compute_firewall" "allow_egress" {
  name      = "allow-egress-gtfs-poller"
  network   = "default"
  direction = "EGRESS"

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["gtfs-poller"]
}
