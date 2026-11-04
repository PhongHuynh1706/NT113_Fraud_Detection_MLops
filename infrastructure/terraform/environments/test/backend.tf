terraform {
  backend "local" {
    path = "../../tfstate/test/terraform.tfstate"
  }
}
