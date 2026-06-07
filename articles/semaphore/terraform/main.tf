terraform {
  required_providers {
    semaphoreui = {
      source  = "semaphoreui/semaphore"
      version = "~> 0.3"
    }
  }
}

provider "semaphoreui" {
  api_base_url = "http://localhost:3000/api"
  api_token    = "gto5yf35phh0rp5rd-5vuqq3jwusrkt_2pdf8x-bd2a="
}

resource "semaphoreui_project" "backup" {
  name = "backup"
}

# Keys

resource "semaphoreui_project_key" "none" {
  project_id = semaphoreui_project.backup.id
  name       = "none"
  none       = {}
}

resource "semaphoreui_project_key" "id-rsa-rocky" {
  project_id = semaphoreui_project.backup.id
  name       = "id-rsa-rocky"
  ssh = {
    login       = "rocky"
    private_key = file("./certs/id_rsa")
  }
}

# Repositories

resource "semaphoreui_project_repository" "postgres-backup" {
  project_id = semaphoreui_project.backup.id
  name       = "postgres-backup"
  url        = "https://gitlab.ops.com/backup/postgres_backup"
  branch     = "main"
  ssh_key_id = semaphoreui_project_key.none.id
}

# Environments

resource "semaphoreui_project_environment" "empty" {
  project_id = semaphoreui_project.backup.id
  name       = "empty"
}

resource "semaphoreui_project_environment" "postgres-backup" {
  project_id = semaphoreui_project.backup.id
  name       = "postgres-backup"
  variables = {
    ansible_become_password = "password"
    target_list_all         = "{{ hostvars['all-in-one'].target_list }}"
  }
}

# Inventories

resource "semaphoreui_project_inventory" "postgres-backup-create" {
  project_id = semaphoreui_project.backup.id
  name       = "postgres-backup-create"
  ssh_key_id = semaphoreui_project_key.id-rsa-rocky.id
  file = {
    path          = "inventory.yml"
    repository_id = semaphoreui_project_repository.postgres-backup.id
  }
}


resource "semaphoreui_project_inventory" "postgres-backup-download" {
  project_id = semaphoreui_project.backup.id
  name       = "postgres-backup-download"
  ssh_key_id = semaphoreui_project_key.id-rsa-rocky.id
  file = {
    path          = "inventory.yml"
    repository_id = semaphoreui_project_repository.postgres-backup.id
  }
}

# Task Templates

resource "semaphoreui_project_template" "postgres-backup-create" {
  project_id     = semaphoreui_project.backup.id
  name           = "postgres-backup-create"
  playbook       = "remote_create_backup.yml"
  repository_id  = semaphoreui_project_repository.postgres-backup.id
  inventory_id   = semaphoreui_project_inventory.postgres-backup-create.id
  environment_id = semaphoreui_project_environment.postgres-backup.id
}

resource "semaphoreui_project_template" "postgres-backup-download" {
  project_id     = semaphoreui_project.backup.id
  name           = "postgres-backup-download"
  playbook       = "remote_copy_backup.yml"
  repository_id  = semaphoreui_project_repository.postgres-backup.id
  inventory_id   = semaphoreui_project_inventory.postgres-backup-download.id
  environment_id = semaphoreui_project_environment.postgres-backup.id
}

