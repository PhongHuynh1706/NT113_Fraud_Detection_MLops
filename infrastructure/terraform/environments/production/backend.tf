terraform {
  backend "local" {
    path = "../../tfstate/production/terraform.tfstate"
  }
}
