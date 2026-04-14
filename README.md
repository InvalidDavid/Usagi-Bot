
[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stars][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![License][license-shield]][license-url]
[![Discord][discord-shield]][discord-url]

<br />
<div align="center">
  <a href="https://github.com/othneildrew/Best-README-Template">
    <img src="ignore/logo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">Best-README-Template</h3>

  <p align="center">
    A simple private discord Bot with many features!
    <br />
    <a href="https://github.com/InvalidDavid/Usagi-Bot"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://discord.com/oauth2/authorize?client_id=1398686204228014091&permissions=8&integration_type=0&scope=bot">View Demo (Bot Link)</a>
    &middot;
    <a href="https://github.com/InvalidDavid/Usagi-Bot/issues/new?template=--bug-report-%F0%9F%90%9E.md">Report Bug</a>
    &middot;
    <a href="https://github.com/InvalidDavid/Usagi-Bot/issues/new?template=feature-request-%F0%9F%9A%80.md">Request Feature</a>
  </p>
</div>

<!-- ABOUT THE PROJECT -->
## About The Project

Simply rewritten and up to date code with many more featuers manga bot which got as well modernized, forked from: [![Github][forked-shield]][forked-url].

...

<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- GETTING STARTED -->
## Getting Started

This is an example of how you may give instructions on setting up your project locally.
To get a local copy up and running follow these simple example steps.

### Prerequisites

This is an example of how to list things you need to use the software and how to install them.
* npm
  ```sh
  pip install
  ```

### Installation

1. Get a the essential data / tokesn for the `.env` from [Discord Developer Site](https://discord.com/developers/home)
2. Clone the repo
   ```sh
   git clone https://github.com/InvalidDavid/Usagi-Bot.git
   ```
3. Install packages (Python 3.13 not 3.14 due to compatibility issues)
   ```sh
   pip install -r requirements.txt
   ```
4. Enter your data in `.env`
   ```py
    TOKEN=#bot token
    GUILDS=#guild id
    OWNER=#same principle as below
    FORUM_ID=# WORKS ONLY FOR ONE SINGLE CHANNEL NOT MULTIPLE ONES
    MOD_ROLE_IDS=
    ADMIN_ROLE_IDS= # role ids, if multiple ones split them with a ,
    WEBHOOK_URL= #webhook url, not required
    ERROREMOJI="❌" # error emoji
    SUPPORT_SERVER="https://github.com/InvalidDavid/Usagi-Bot"
   ```
6. Check if you have all the folders needed
   ```sh
   - Data
   - cog
   - utils
     - error
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

> [!NOTE]
> - Forum and role settings are read safely from `.env` through the shared config loader.
> - Don`t forget to install the package from the requirements.txt.
> - As well the right Data in `.env`.



<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/InvalidDavid/Usagi-Bot.svg?style=for-the-badge
[contributors-url]: https://github.com/InvalidDavid/Usagi-Bot/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/InvalidDavid/Usagi-Bot.svg?style=for-the-badge
[forks-url]: https://github.com/InvalidDavid/Usagi-Bot/network/members
[stars-shield]: https://img.shields.io/github/stars/InvalidDavid/Usagi-Bot.svg?style=for-the-badge
[stars-url]: https://github.com/InvalidDavid/Usagi-Bot/stargazers
[issues-shield]: https://img.shields.io/github/issues/InvalidDavid/Usagi-Bot.svg?style=for-the-badge
[issues-url]: https://github.com/InvalidDavid/Usagi-Bot/issues
[license-shield]:https://img.shields.io/github/license/InvalidDavid/Usagi-Bot.svg?style=for-the-badge
[license-url]: https://github.com/InvalidDavid/Usagi-Bot/blob/main/LICENSE
[discord-shield]: https://img.shields.io/badge/-Discord-black.svg?style=for-the-badge&logo=discord&colorB=555
[discord-url]: https://discord.gg/FRvn4X2Q5y
[forked-shield]: https://img.shields.io/badge/-Github-black.svg?style=for-the-badge&logo=github&colorB=555
[forked-url]: https://github.com/KotatsuApp/Emanon-GO
